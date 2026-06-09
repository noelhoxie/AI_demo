# Databricks notebook source
# MAGIC %md
# MAGIC # Gold — gold_material_fuzzy_match
# MAGIC Pairwise similarity scoring for all SKU descriptions using three methods:
# MAGIC - **Levenshtein** — character edit distance
# MAGIC - **Jaro-Winkler** — prefix-aware string similarity
# MAGIC - **ai_similarity()** — Databricks AI semantic similarity (Foundation Model)
# MAGIC
# MAGIC Each pair receives a composite weighted score and a match tier (EXACT / HIGH / MEDIUM / LOW).
# MAGIC Run `gold_demand_forecast` first to ensure the source table exists.

# COMMAND ----------

dbutils.widgets.text("catalog", "demo_nah_catalog", "Catalog")
dbutils.widgets.text("schema",  "supplychain_solutionstudio", "Schema")
catalog = (dbutils.widgets.get("catalog") or "demo_nah_catalog").strip()
schema  = (dbutils.widgets.get("schema")  or "supplychain_solutionstudio").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TABLE `{catalog}`.`{schema}`.gold_material_fuzzy_match AS

-- ── Step 1: distinct SKU descriptions from the deduplicated forecast table ──
WITH distinct_skus AS (
  SELECT DISTINCT sku_id, TRIM(sku_description) AS sku_description
  FROM `{catalog}`.`{schema}`.gold_demand_forecast
),

-- ── Step 2: all unique pairs (A < B avoids self-pairs and reverse dupes) ────
pairs AS (
  SELECT
    a.sku_id          AS sku_id_a,
    a.sku_description AS description_a,
    b.sku_id          AS sku_id_b,
    b.sku_description AS description_b
  FROM distinct_skus a
  JOIN distinct_skus b ON a.sku_id < b.sku_id
),

-- ── Step 3: compute similarity scores ───────────────────────────────────────
scored AS (
  SELECT
    sku_id_a,
    description_a,
    sku_id_b,
    description_b,

    -- Raw Levenshtein edit distance (0 = identical)
    levenshtein(
      LOWER(description_a),
      LOWER(description_b)
    ) AS levenshtein_distance,

    -- Levenshtein similarity normalised to 0–1
    ROUND(
      1.0 - levenshtein(LOWER(description_a), LOWER(description_b))
            / CAST(GREATEST(LENGTH(description_a), LENGTH(description_b)) AS DOUBLE),
      4
    ) AS levenshtein_similarity,

    -- Jaro-Winkler similarity 0–1 (rewards common prefix, good for typos)
    ROUND(
      jarowinkler_similarity(LOWER(description_a), LOWER(description_b)),
      4
    ) AS jarowinkler_similarity,

    -- Databricks AI semantic similarity 0–1
    -- Uses Foundation Model embeddings — understands meaning, not just characters
    ROUND(
      ai_similarity(description_a, description_b),
      4
    ) AS ai_similarity_score

  FROM pairs
),

-- ── Step 4: composite score + match tier ────────────────────────────────────
final AS (
  SELECT
    sku_id_a,
    description_a,
    sku_id_b,
    description_b,
    levenshtein_distance,
    levenshtein_similarity,
    jarowinkler_similarity,
    ai_similarity_score,

    -- Weighted composite: AI carries most weight as it understands semantics
    ROUND(
      (ai_similarity_score      * 0.50) +
      (jarowinkler_similarity   * 0.30) +
      (levenshtein_similarity   * 0.20),
      4
    ) AS composite_score,

    -- Match tier for easy filtering in Genie / dashboards
    CASE
      WHEN levenshtein_distance = 0                                                THEN 'EXACT'
      WHEN (ai_similarity_score * 0.50 + jarowinkler_similarity * 0.30
            + levenshtein_similarity * 0.20) >= 0.85                              THEN 'HIGH'
      WHEN (ai_similarity_score * 0.50 + jarowinkler_similarity * 0.30
            + levenshtein_similarity * 0.20) >= 0.70                              THEN 'MEDIUM'
      ELSE                                                                         'LOW'
    END AS match_tier,

    current_timestamp() AS scored_at

  FROM scored
)

SELECT * FROM final
ORDER BY composite_score DESC
""")

# COMMAND ----------

result = spark.table(f"`{catalog}`.`{schema}`.gold_material_fuzzy_match")
total  = result.count()
tiers  = result.groupBy("match_tier").count().orderBy("match_tier").collect()

print(f"gold_material_fuzzy_match written — {total} pairs scored")
for row in tiers:
    print(f"  {row['match_tier']}: {row['count']} pairs")

# COMMAND ----------

# Show top potential duplicates (HIGH + EXACT matches)
display(
    result.filter("match_tier IN ('EXACT', 'HIGH')")
          .orderBy("composite_score", ascending=False)
          .limit(50)
)
