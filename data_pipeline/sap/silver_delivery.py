# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Silver — sap_silver_delivery
# MAGIC LIKP + LIPS join with business-friendly column names and derived fields.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql import functions as F

likp = spark.table(f"`{catalog}`.`{schema}`.bronze_likp")
lips = spark.table(f"`{catalog}`.`{schema}`.bronze_lips")

sap_silver_delivery = (
    lips.alias("p")
    .join(likp.alias("h"), F.col("p.vbeln") == F.col("h.vbeln"), "left")
    .select(
        F.col("p.vbeln").alias("delivery_number"),
        F.col("p.posnr").alias("line_item_number"),
        F.col("p.matnr").alias("material_number"),
        F.col("p.lfimg").alias("delivered_quantity"),
        F.col("p.vrkme").alias("unit_of_measure"),
        F.col("h.kunnr").alias("customer_number"),
        F.expr("try_to_date(h.lfdat, 'yyyy-MM-dd')").alias("planned_delivery_date"),
        F.expr("try_to_date(h.wadat_ist, 'yyyy-MM-dd')").alias("actual_delivery_date"),
        F.col("h.tragr").alias("shipping_carrier"),
    )
    .withColumn(
        "delivery_variance_days",
        F.when(
            F.col("actual_delivery_date").isNotNull() & F.col("planned_delivery_date").isNotNull(),
            F.datediff(F.col("actual_delivery_date"), F.col("planned_delivery_date")),
        ).otherwise(F.lit(None)),
    )
    .withColumn(
        "on_time_delivery",
        F.when(
            F.col("actual_delivery_date").isNotNull() & F.col("planned_delivery_date").isNotNull(),
            F.col("actual_delivery_date") <= F.col("planned_delivery_date"),
        ).otherwise(F.lit(None)),
    )
    .withColumn(
        "delivery_status",
        F.when(F.col("actual_delivery_date").isNull(), F.lit("Pending"))
        .when(F.col("on_time_delivery") == True, F.lit("On Time"))
        .otherwise(F.lit("Late")),
    )
)

sap_silver_delivery.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.sap_silver_delivery"
)
display(sap_silver_delivery.limit(10))
