"""
Setup script for Equipment Manuals RAG pipeline.

Run this notebook/script in a Databricks cluster after generating PDFs with
generate_equipment_manuals.py.

Steps:
  1. Read PDFs from UC Volume
  2. Parse and chunk text
  3. Write chunks to a Delta table
  4. Create / sync a Vector Search index
  5. Register a simple RAG chain as a Model Serving endpoint

Requirements (install on cluster):
  %pip install pypdf databricks-vectorsearch mlflow langchain-community
"""

import os
import re
import hashlib
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CATALOG   = "demo_nah_catalog"
SCHEMA    = "mfg_docs"
VOLUME    = "manuals"
CHUNK_TABLE    = f"{CATALOG}.{SCHEMA}.manual_chunks"
VS_ENDPOINT    = "mfg-manuals-vs"
VS_INDEX       = f"{CATALOG}.{SCHEMA}.manual_chunks_index"
SERVING_EP     = "mfg-manuals-rag"
EMBED_MODEL    = "databricks-gte-large-en"
LLM_MODEL      = "databricks-meta-llama-3-3-70b-instruct"
VOLUME_PATH    = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}"

CHUNK_SIZE     = 600   # tokens (approximate via words)
CHUNK_OVERLAP  = 80


# ---------------------------------------------------------------------------
# 1. Parse PDFs → text chunks
# ---------------------------------------------------------------------------

def _chunk_text(text: str, source: str, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Split text into overlapping word-based chunks."""
    words = text.split()
    chunks = []
    start = 0
    idx = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])
        chunk_id = hashlib.md5(f"{source}:{idx}".encode()).hexdigest()
        chunks.append({
            "chunk_id":   chunk_id,
            "source":     source,
            "chunk_index": idx,
            "content":    chunk,
        })
        idx += 1
        start += chunk_size - overlap
    return chunks


def load_chunks_from_volume():
    """Read all PDFs from the UC Volume and return a list of chunk dicts."""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError("Install pypdf: %pip install pypdf")

    all_chunks = []
    pdf_dir = Path(VOLUME_PATH)
    pdf_files = sorted(pdf_dir.glob("*.pdf"))
    print(f"Found {len(pdf_files)} PDFs in {VOLUME_PATH}")

    for pdf_path in pdf_files:
        print(f"  Parsing {pdf_path.name} ...")
        reader = PdfReader(str(pdf_path))
        full_text = "\n".join(
            page.extract_text() or "" for page in reader.pages
        )
        # normalise whitespace
        full_text = re.sub(r"\s+", " ", full_text).strip()
        chunks = _chunk_text(full_text, source=pdf_path.name)
        all_chunks.extend(chunks)
        print(f"    → {len(chunks)} chunks")

    print(f"Total chunks: {len(all_chunks)}")
    return all_chunks


# ---------------------------------------------------------------------------
# 2. Write chunks to Delta table (with embedding source column)
# ---------------------------------------------------------------------------

def write_chunks_to_delta(spark, chunks):
    """Write chunk list to a managed Delta table ready for Vector Search."""
    from pyspark.sql import Row
    from pyspark.sql.types import StructType, StructField, StringType, IntegerType

    schema = StructType([
        StructField("chunk_id",    StringType(),  False),
        StructField("source",      StringType(),  False),
        StructField("chunk_index", IntegerType(), False),
        StructField("content",     StringType(),  False),
    ])

    df = spark.createDataFrame([Row(**c) for c in chunks], schema=schema)
    (
        df.write
          .format("delta")
          .mode("overwrite")
          .option("overwriteSchema", "true")
          .option("delta.enableChangeDataFeed", "true")
          .saveAsTable(CHUNK_TABLE)
    )
    print(f"Wrote {df.count()} rows to {CHUNK_TABLE}")

    # Enable Change Data Feed (required for VS sync)
    spark.sql(f"""
        ALTER TABLE {CHUNK_TABLE}
        SET TBLPROPERTIES (delta.enableChangeDataFeed = true)
    """)
    print("CDF enabled.")


# ---------------------------------------------------------------------------
# 3. Create Vector Search endpoint + index
# ---------------------------------------------------------------------------

def create_vector_search_index():
    """Create (or update) the VS endpoint and Delta Sync index."""
    from databricks.vector_search.client import VectorSearchClient

    vsc = VectorSearchClient(disable_notice=True)

    # Create endpoint if it doesn't exist
    existing_endpoints = [e["name"] for e in vsc.list_endpoints().get("endpoints", [])]
    if VS_ENDPOINT not in existing_endpoints:
        print(f"Creating VS endpoint '{VS_ENDPOINT}' ...")
        vsc.create_endpoint(name=VS_ENDPOINT, endpoint_type="STANDARD")
    else:
        print(f"VS endpoint '{VS_ENDPOINT}' already exists.")

    # Create or sync index
    existing_indexes = [i["name"] for i in vsc.list_indexes(VS_ENDPOINT).get("vector_indexes", [])]
    if VS_INDEX not in existing_indexes:
        print(f"Creating VS index '{VS_INDEX}' ...")
        vsc.create_delta_sync_index(
            endpoint_name=VS_ENDPOINT,
            index_name=VS_INDEX,
            source_table_name=CHUNK_TABLE,
            pipeline_type="TRIGGERED",
            primary_key="chunk_id",
            embedding_source_column="content",
            embedding_model_endpoint_name=EMBED_MODEL,
        )
    else:
        print(f"VS index '{VS_INDEX}' already exists — triggering sync ...")
        vsc.get_index(VS_ENDPOINT, VS_INDEX).sync()

    print("Vector Search index ready.")


# ---------------------------------------------------------------------------
# 4. Register RAG chain as a Model Serving endpoint
# ---------------------------------------------------------------------------

RAG_CHAIN_CODE = '''
import mlflow
from databricks.vector_search.client import VectorSearchClient
from databricks.sdk import WorkspaceClient
import openai, os

CATALOG  = "{catalog}"
SCHEMA   = "{schema}"
VS_EP    = "{vs_endpoint}"
VS_IDX   = "{vs_index}"
LLM_EP   = "{llm_model}"

mlflow.set_registry_uri("databricks-uc")

class ManualsRagChain(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        self.vsc = VectorSearchClient(disable_notice=True)
        self.index = self.vsc.get_index(VS_EP, VS_IDX)
        w = WorkspaceClient()
        host = "https://" + w.config.host.rstrip("/")
        self.client = openai.OpenAI(
            base_url=f"{{host}}/serving-endpoints",
            api_key=w.config.token,
        )

    def predict(self, context, model_input):
        question = (
            model_input["question"][0]
            if hasattr(model_input, "__getitem__")
            else str(model_input)
        )
        results = self.index.similarity_search(
            query_text=question,
            columns=["content", "source"],
            num_results=4,
        )
        rows = results.get("result", {{}}).get("data_array", [])
        context_text = "\\n\\n---\\n\\n".join(r[0] for r in rows)
        sources = list({{r[1] for r in rows}})

        messages = [
            {{
                "role": "system",
                "content": (
                    "You are a manufacturing equipment expert assistant. "
                    "Answer questions using ONLY the provided manual excerpts. "
                    "Be concise and precise. If the answer is not in the excerpts, say so."
                ),
            }},
            {{
                "role": "user",
                "content": f"Manual excerpts:\\n{{context_text}}\\n\\nQuestion: {{question}}",
            }},
        ]
        resp = self.client.chat.completions.create(
            model=LLM_EP,
            messages=messages,
            max_tokens=512,
            temperature=0.1,
        )
        answer = resp.choices[0].message.content.strip()
        return {{"answer": answer, "sources": sources}}
'''.format(
    catalog=CATALOG,
    schema=SCHEMA,
    vs_endpoint=VS_ENDPOINT,
    vs_index=VS_INDEX,
    llm_model=LLM_MODEL,
)


def register_rag_chain():
    """Log the RAG chain to MLflow and register in Unity Catalog."""
    import mlflow

    mlflow.set_registry_uri("databricks-uc")
    model_name = f"{CATALOG}.{SCHEMA}.manuals_rag_chain"

    # Write chain file temporarily
    chain_path = "/tmp/manuals_rag_chain.py"
    with open(chain_path, "w") as f:
        f.write(RAG_CHAIN_CODE)

    with mlflow.start_run(run_name="manuals-rag-chain"):
        logged = mlflow.pyfunc.log_model(
            artifact_path="chain",
            python_model=chain_path,
            registered_model_name=model_name,
            pip_requirements=[
                "databricks-vectorsearch",
                "databricks-sdk",
                "openai",
                "mlflow",
            ],
            input_example={"question": ["What is the maintenance interval for the welding robot?"]},
        )
    print(f"Logged model: {logged.model_uri}")
    return model_name


def deploy_serving_endpoint(model_name: str):
    """Create or update the model serving endpoint."""
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.serving import (
        EndpointCoreConfigInput,
        ServedModelInput,
        ServedModelInputWorkloadSize,
    )

    w = WorkspaceClient()

    # Get latest version
    versions = w.registered_models.list_versions(full_name=model_name)
    latest = max(int(v.version) for v in versions)
    print(f"Latest model version: {latest}")

    config = EndpointCoreConfigInput(
        served_models=[
            ServedModelInput(
                model_name=model_name,
                model_version=str(latest),
                workload_size=ServedModelInputWorkloadSize.SMALL,
                scale_to_zero_enabled=True,
            )
        ]
    )

    existing = [e.name for e in w.serving_endpoints.list()]
    if SERVING_EP in existing:
        print(f"Updating endpoint '{SERVING_EP}' ...")
        w.serving_endpoints.update_config_and_wait(name=SERVING_EP, served_models=config.served_models)
    else:
        print(f"Creating endpoint '{SERVING_EP}' ...")
        w.serving_endpoints.create_and_wait(name=SERVING_EP, config=config)

    print(f"Serving endpoint '{SERVING_EP}' is ready.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(spark):
    print("=== Step 1: Load and parse PDFs ===")
    chunks = load_chunks_from_volume()

    print("\n=== Step 2: Write chunks to Delta ===")
    write_chunks_to_delta(spark, chunks)

    print("\n=== Step 3: Create Vector Search index ===")
    create_vector_search_index()

    print("\n=== Step 4: Register RAG chain ===")
    model_name = register_rag_chain()

    print("\n=== Step 5: Deploy serving endpoint ===")
    deploy_serving_endpoint(model_name)

    print("\nAll done! Serving endpoint:", SERVING_EP)


# Run in Databricks notebook: main(spark)
if __name__ == "__main__":
    # Local test — just parse (no Spark)
    chunks = load_chunks_from_volume()
    print(f"Parsed {len(chunks)} total chunks.")
