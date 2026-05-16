#!/usr/bin/env python3
"""
E-Coat Adhesion Defect Detection Model — sklearn edition
=========================================================
Trains a binary image classifier (clean=0 / defective=1) using:
  • Feature extraction: color histograms, texture stats, spatial statistics
  • Data augmentation: 8× per image (flips + 90° rotations) → 80 training samples
  • Classifier: SVM (RBF kernel) with class-weight balancing
  • MLflow: logs params, metrics, and registers model to UC Model Registry

Usage (local — sklearn + mlflow required):
  python3 train_defect_model.py

Usage (Databricks cluster with ML runtime — full PyTorch version):
  See train_defect_model_pytorch.py (notebook upload)

Environment variables:
  DATABRICKS_HOST        — workspace URL (for MLflow tracking)
  DATABRICKS_TOKEN       — PAT
  UC_CATALOG             — default: demo_nah_catalog
  UC_SCHEMA              — default: mfg_vision
  UC_VOLUME              — default: inspection_images
  MODEL_NAME             — UC registered model name
"""

import io
import os
import sys
import math
import random
import requests
import warnings
warnings.filterwarnings("ignore")

import numpy as np
from PIL import Image

import mlflow
import mlflow.sklearn
from mlflow.models.signature import infer_signature

from sklearn.svm import SVC
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import (classification_report, confusion_matrix,
                              roc_auc_score, accuracy_score)
from sklearn.model_selection import StratifiedKFold, cross_val_score

# ── Config ─────────────────────────────────────────────────────────────────────
HOST     = os.environ.get("DATABRICKS_HOST", "https://fevm-demo-nah.cloud.databricks.com").rstrip("/")
TOKEN    = os.environ.get("DATABRICKS_TOKEN", "os.environ.get("DATABRICKS_TOKEN", "")")
CATALOG  = os.environ.get("UC_CATALOG",  "demo_nah_catalog")
SCHEMA   = os.environ.get("UC_SCHEMA",   "mfg_vision")
VOLUME   = os.environ.get("UC_VOLUME",   "inspection_images")
MODEL_UC = os.environ.get("MODEL_NAME",  f"{CATALOG}.{SCHEMA}.ecoat_defect_classifier")
EXP_NAME = "/Users/noel.hoxie@databricks.com/ecoat-defect-detection"
IMG_SIZE = 64   # Resize to 64×64 for feature extraction

# Ground truth labels (matches generate_inspection_images.py)
LABELS = {
    "insp_001": 0, "insp_002": 0, "insp_003": 1,
    "insp_004": 0, "insp_005": 0, "insp_006": 0,
    "insp_007": 1, "insp_008": 0, "insp_009": 0, "insp_010": 0,
}
CLASS_NAMES = ["clean", "defective"]


# ── Image loading ──────────────────────────────────────────────────────────────

def load_image_from_uc(filename):
    """Fetch image from UC Volume via Files API; fall back to local static dir."""
    if TOKEN:
        try:
            hdrs = {"Authorization": f"Bearer {TOKEN}"}
            r = requests.get(
                f"{HOST}/api/2.0/fs/files/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}/{filename}",
                headers=hdrs, timeout=20,
            )
            if r.status_code == 200:
                return Image.open(io.BytesIO(r.content)).convert("RGB")
        except Exception:
            pass
    local = os.path.join(os.path.dirname(__file__), "static", "img", "inspection", filename)
    if os.path.exists(local):
        return Image.open(local).convert("RGB")
    raise FileNotFoundError(f"Image not found: {filename}")


# ── Feature extraction ────────────────────────────────────────────────────────

def extract_features(pil_img):
    """
    Extract 135-dimensional feature vector from an RGB image.
    Features designed to detect E-Coat adhesion defects (dark, irregular patches
    with lighter halo on painted body panel surfaces).
    """
    img = pil_img.resize((IMG_SIZE, IMG_SIZE), Image.LANCZOS)
    arr = np.array(img).astype(np.float32) / 255.0  # shape (64, 64, 3)

    feats = []

    # 1. Per-channel global mean + std  (6 features)
    for c in range(3):
        ch = arr[:, :, c]
        feats += [ch.mean(), ch.std()]

    # 2. Per-channel colour histogram, 16 bins (48 features)
    for c in range(3):
        hist, _ = np.histogram(arr[:, :, c], bins=16, range=(0.0, 1.0))
        hist = hist.astype(np.float32) / hist.sum()
        feats += hist.tolist()

    # 3. Dark-pixel ratio — E-Coat delamination creates dark patches (1 feature)
    # A pixel is "dark" if all channels are below 0.28
    dark_mask = (arr < 0.28).all(axis=2)
    feats.append(float(dark_mask.mean()))

    # 4. Contrast ratio dark/bright pixels (1 feature)
    bright_mask = (arr > 0.72).all(axis=2)
    feats.append(float(dark_mask.sum()) / max(1, float(bright_mask.sum()) + 1e-6))

    # 5. Gradient magnitude statistics (2 features) — defects have strong local edges
    gray = arr.mean(axis=2)
    gy, gx = np.gradient(gray)
    grad = np.sqrt(gx**2 + gy**2)
    feats += [grad.mean(), grad.std()]

    # 6. Quadrant mean brightness — 4 quadrants × 3 channels (12 features)
    h, w = IMG_SIZE, IMG_SIZE
    mid_h, mid_w = h // 2, w // 2
    for r0, r1 in [(0, mid_h), (mid_h, h)]:
        for c0, c1 in [(0, mid_w), (mid_w, w)]:
            region = arr[r0:r1, c0:c1]
            for ch in range(3):
                feats.append(float(region[:, :, ch].mean()))

    # 7. Local variance in centre (30% of image) vs edges — defects often central (2 features)
    pad = int(IMG_SIZE * 0.15)
    centre = arr[pad:-pad, pad:-pad]
    edge_pixels = np.concatenate([arr[:pad, :].reshape(-1, 3),
                                   arr[-pad:, :].reshape(-1, 3),
                                   arr[:, :pad, :].reshape(-1, 3),
                                   arr[:, -pad:, :].reshape(-1, 3)])
    feats += [float(centre.var()), float(edge_pixels.var())]

    # 8. Min / Max intensity range (2 features)
    feats += [float(arr.min()), float(arr.max())]

    # 9. Skewness approximation per channel (3 features)
    for c in range(3):
        ch = arr[:, :, c]
        mu, sigma = ch.mean(), ch.std() + 1e-6
        skew = float(((ch - mu) ** 3).mean() / sigma ** 3)
        feats.append(skew)

    return np.array(feats, dtype=np.float32)


# ── Augmentation ──────────────────────────────────────────────────────────────

def augment_image(pil_img):
    """Generate 8 augmented variants: original + 3 rotations + 4 flips."""
    variants = [pil_img]
    for angle in [90, 180, 270]:
        variants.append(pil_img.rotate(angle))
    flipped_h = pil_img.transpose(Image.FLIP_LEFT_RIGHT)
    flipped_v = pil_img.transpose(Image.FLIP_TOP_BOTTOM)
    variants.append(flipped_h)
    variants.append(flipped_v)
    variants.append(flipped_h.rotate(90))
    variants.append(flipped_v.rotate(90))
    return variants  # 8 images


# ── Build dataset ────────────────────────────────────────────────────────────

def build_dataset():
    print("Loading images from UC Volume…")
    X, y = [], []
    for img_id, label in sorted(LABELS.items()):
        fname = f"{img_id}.png"
        try:
            img = load_image_from_uc(fname)
            for aug in augment_image(img):
                feats = extract_features(aug)
                X.append(feats)
                y.append(label)
            tag = "DEFECT" if label == 1 else "clean "
            print(f"  {fname}  [{tag}]  → 8 augmented samples")
        except FileNotFoundError as e:
            print(f"  SKIP {fname}: {e}")

    return np.array(X), np.array(y)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\nE-Coat Defect Classifier — Training")
    print(f"  UC Volume : /Volumes/{CATALOG}/{SCHEMA}/{VOLUME}")
    print(f"  MLflow    : {HOST}/mlflow")
    print(f"  Model     : {MODEL_UC}\n")

    # ── Dataset ───────────────────────────────────────────────────────────
    X, y = build_dataset()
    n_def = int(y.sum())
    n_cln = int((y == 0).sum())
    print(f"\nDataset: {len(X)} samples  ({n_cln} clean, {n_def} defective)")
    print(f"Feature dim: {X.shape[1]}")

    # ── Cross-validation for metrics ─────────────────────────────────────
    pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("svm", SVC(kernel="rbf", C=10, gamma="scale",
                    class_weight="balanced", probability=True, random_state=42)),
    ])

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = cross_val_score(pipe, X, y, cv=cv, scoring="accuracy")
    print(f"\n5-fold CV accuracy: {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")

    # ── Final fit on all data ────────────────────────────────────────────
    pipe.fit(X, y)
    y_pred = pipe.predict(X)
    y_prob = pipe.predict_proba(X)[:, 1]
    train_acc = accuracy_score(y, y_pred)
    try:
        auc = roc_auc_score(y, y_prob)
    except ValueError:
        auc = float("nan")

    print(f"Train accuracy: {train_acc:.3f}  AUC: {auc:.3f}")
    print("\nClassification report:")
    print(classification_report(y, y_pred, target_names=CLASS_NAMES))

    # ── MLflow logging ───────────────────────────────────────────────────
    if TOKEN:
        try:
            os.environ["DATABRICKS_HOST"]  = HOST
            os.environ["DATABRICKS_TOKEN"] = TOKEN
            mlflow.set_tracking_uri("databricks")
            mlflow.set_registry_uri("databricks-uc")
            mlflow.set_experiment(EXP_NAME)
        except Exception as ex:
            print(f"  MLflow setup warning: {ex}")
    else:
        pass

    sample_input  = X[:2]
    sample_output = pipe.predict(sample_input)
    signature = infer_signature(sample_input, sample_output)

    with mlflow.start_run(run_name="ecoat-defect-svm") as run:
        mlflow.log_params({
            "model_type":       "SVM-RBF",
            "feature_dim":      X.shape[1],
            "aug_per_image":    8,
            "train_samples":    len(X),
            "source_images":    len(LABELS),
            "defect_class":     "E-Coat Adhesion Failure",
            "svm_C":            10,
            "svm_gamma":        "scale",
            "class_weight":     "balanced",
            "uc_volume":        f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}",
        })
        mlflow.log_metrics({
            "cv_acc_mean":  round(float(cv_scores.mean()), 4),
            "cv_acc_std":   round(float(cv_scores.std()),  4),
            "train_acc":    round(train_acc, 4),
            "roc_auc":      round(float(auc), 4) if not math.isnan(auc) else 0.0,
        })

        model_info = mlflow.sklearn.log_model(
            pipe,
            artifact_path="model",
            signature=signature,
            input_example=sample_input,
            registered_model_name=MODEL_UC,
        )

        print(f"\n{'='*60}")
        print(f"Model logged and registered")
        print(f"  MLflow Run ID : {run.info.run_id}")
        print(f"  Model URI     : {model_info.model_uri}")
        print(f"  UC Model Name : {MODEL_UC}")
        print(f"{'='*60}")
        print(f"\nNext steps:")
        print(f"  1. Databricks → Models → {MODEL_UC} → Serving")
        print(f"  2. Create endpoint → Set VISION_MODEL_ENDPOINT in app.yaml")
        print(f"  3. The app will call the endpoint for real-time inference")
        print(f"{'='*60}\n")

    return run.info.run_id


if __name__ == "__main__":
    main()
