# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Silver — sap_silver_orders
# MAGIC VBAK + VBAP join with business-friendly column names and derived fields.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql import functions as F

vbak = spark.table(f"`{catalog}`.`{schema}`.bronze_vbak")
vbap = spark.table(f"`{catalog}`.`{schema}`.bronze_vbap")

sap_silver_orders = (
    vbap.alias("p")
    .join(vbak.alias("h"), F.col("p.vbeln") == F.col("h.vbeln"), "left")
    .select(
        F.col("p.vbeln").alias("sales_order_number"),
        F.col("p.posnr").alias("line_item_number"),
        F.col("p.matnr").alias("material_number"),
        F.col("p.kwmeng").alias("order_quantity"),
        F.col("p.vrkme").alias("unit_of_measure"),
        F.col("p.netwr").alias("net_value_usd"),
        F.col("p.edatu").alias("requested_delivery_date"),
        F.col("p.absta").alias("rejection_status"),
        F.col("h.vkorg").alias("sales_organization"),
        F.col("h.vtweg").alias("distribution_channel"),
        F.col("h.kunnr").alias("customer_number"),
        F.col("h.audat").alias("order_date"),
    )
    .withColumn(
        "is_rejected",
        F.col("rejection_status").isNotNull() & (F.col("rejection_status") != ""),
    )
    .withColumn(
        "days_to_delivery",
        F.datediff(
            F.expr("try_to_date(requested_delivery_date, 'yyyy-MM-dd')"),
            F.expr("try_to_date(order_date, 'yyyy-MM-dd')"),
        ),
    )
    .withColumn(
        "order_year_month",
        F.date_format(F.expr("try_to_date(order_date, 'yyyy-MM-dd')"), "yyyy-MM"),
    )
)

sap_silver_orders.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.sap_silver_orders"
)
display(sap_silver_orders.limit(10))
