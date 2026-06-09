# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Silver — sap_silver_procurement
# MAGIC EKKO + EKPO join with business-friendly column names and derived fields.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql import functions as F

ekko = spark.table(f"`{catalog}`.`{schema}`.bronze_ekko")
ekpo = spark.table(f"`{catalog}`.`{schema}`.bronze_ekpo")

sap_silver_procurement = (
    ekpo.alias("p")
    .join(ekko.alias("h"), F.col("p.ebeln") == F.col("h.ebeln"), "left")
    .select(
        F.col("p.ebeln").alias("purchase_order_number"),
        F.col("p.ebelp").alias("po_line_item_number"),
        F.col("p.matnr").alias("material_number"),
        F.col("p.menge").alias("ordered_quantity"),
        F.col("p.meins").alias("unit_of_measure"),
        F.col("p.netwr").alias("net_value_usd"),
        F.col("p.werks").alias("plant"),
        F.col("p.lgort").alias("storage_location"),
        F.col("p.eindt").alias("scheduled_delivery_date"),
        F.col("h.bukrs").alias("company_code"),
        F.col("h.lifnr").alias("supplier_number"),
        F.col("h.bsart").alias("po_type"),
        F.col("h.aedat").alias("po_creation_date"),
    )
    .withColumn(
        "unit_price",
        F.when(F.col("ordered_quantity") > 0, F.col("net_value_usd") / F.col("ordered_quantity")).otherwise(F.lit(None)),
    )
    .withColumn(
        "days_until_delivery",
        F.datediff(
            F.expr("try_to_date(scheduled_delivery_date, 'yyyy-MM-dd')"),
            F.expr("try_to_date(po_creation_date, 'yyyy-MM-dd')"),
        ),
    )
)

sap_silver_procurement.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.sap_silver_procurement"
)
display(sap_silver_procurement.limit(10))
