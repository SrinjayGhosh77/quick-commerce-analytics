import sqlite3
from pathlib import Path
import pandas as pd

# ============================================================
# BIGBASKET SQL ANALYSIS
# SQLite3 + pandas | 10 sections | 5 KPIs + 5 top questions
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = None
for folder in [SCRIPT_DIR, SCRIPT_DIR.parent, SCRIPT_DIR.parent.parent, Path.cwd(), Path.cwd().parent]:
    if (folder / "cleaned data").is_dir():
        PROJECT_DIR = folder
        break

if PROJECT_DIR is None:
    raise FileNotFoundError(
        "Could not find 'cleaned data'. Keep bigbasket.py inside SDLC Main."
    )

CLEANED_FOLDER = PROJECT_DIR / "cleaned data"
DATABASE_FOLDER = PROJECT_DIR / "database"
DATABASE_FOLDER.mkdir(exist_ok=True)
DATABASE_PATH = DATABASE_FOLDER / "quick_commerce.db"

FILES = {
    "platforms": "01_platforms_cleaned.csv",
    "dark_stores": "02_dark_stores_cleaned.csv",
    "employees": "03_employees_cleaned.csv",
    "products": "04_products_cleaned.csv",
    "customers": "05_customers_cleaned.csv",
    "orders": "06_orders_cleaned.csv",
    "order_items": "07_order_items_cleaned.csv",
    "inventory": "08_inventory_cleaned.csv",
    "logistics": "09_logistics_delivery_cleaned.csv",
    "pnl_monthly": "10_pnl_monthly_cleaned.csv",
}

conn = sqlite3.connect(DATABASE_PATH)


def clean_dataframe(df):
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

    for col in [
        "platform_id", "store_id", "employee_id", "product_id", "customer_id",
        "order_id", "order_item_id", "inventory_id", "delivery_id", "rider_id",
        "pnl_id", "pincode", "launch_year"
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in [
        "sqft_area", "monthly_salary_inr", "mrp", "selling_price", "discount_percent",
        "promised_delivery_min", "actual_delivery_min", "order_value_inr", "discount_inr",
        "quantity", "item_price_inr", "line_total_inr", "stock_units", "reorder_level",
        "distance_km", "delivery_rating", "revenue_inr", "cogs_inr", "delivery_cost_inr",
        "marketing_spend_inr", "employee_cost_inr", "other_opex_inr", "orders_count"
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in ["city", "hq_city"]:
        if col in df.columns:
            df[col] = df[col].astype("string").str.strip().str.title()

    for col in ["order_datetime", "signup_date", "joining_date", "opened_date", "last_restock_date", "expiry_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%Y-%m-%d")

    if "month" in df.columns:
        df["month"] = pd.to_datetime(df["month"], errors="coerce").dt.strftime("%Y-%m")

    return df


# Load all cleaned datasets into SQLite.
for table, filename in FILES.items():
    path = CLEANED_FOLDER / filename
    if not path.exists():
        conn.close()
        raise FileNotFoundError(f"File not found: {path}")
    df = pd.read_csv(path)
    bad_cols = [c for c in df.columns if str(c).lower().startswith("unnamed:")]
    if bad_cols:
        df = df.drop(columns=bad_cols)
    df = clean_dataframe(df)
    df.to_sql(table, conn, if_exists="replace", index=False)

# Find BigBasket safely; source data may contain spaces in the name.
platform = pd.read_sql_query(
    """
    SELECT platform_id, platform_name
    FROM platforms
    WHERE LOWER(REPLACE(TRIM(platform_name), ' ', '')) LIKE '%bigbasket%'
    LIMIT 1
    """,
    conn,
)
if platform.empty:
    conn.close()
    raise ValueError("BigBasket was not found in the platforms table.")

BIGBASKET_PLATFORM_ID = int(platform.iloc[0]["platform_id"])
print(f"BigBasket platform_id: {BIGBASKET_PLATFORM_ID}")

# Safe P&L view: NULL cost fields are treated as zero.
conn.execute("DROP VIEW IF EXISTS pnl_monthly_safe")
conn.execute(
    """
    CREATE VIEW pnl_monthly_safe AS
    SELECT
        pnl_id, platform_id, city, month,
        COALESCE(revenue_inr, 0) AS revenue_inr,
        COALESCE(cogs_inr, 0) AS cogs_inr,
        COALESCE(delivery_cost_inr, 0) AS delivery_cost_inr,
        COALESCE(marketing_spend_inr, 0) AS marketing_spend_inr,
        COALESCE(employee_cost_inr, 0) AS employee_cost_inr,
        COALESCE(other_opex_inr, 0) AS other_opex_inr,
        COALESCE(orders_count, 0) AS orders_count,
        COALESCE(revenue_inr, 0)
        - COALESCE(cogs_inr, 0)
        - COALESCE(delivery_cost_inr, 0)
        - COALESCE(marketing_spend_inr, 0)
        - COALESCE(employee_cost_inr, 0)
        - COALESCE(other_opex_inr, 0) AS profit_inr
    FROM pnl_monthly
    """)
conn.commit()


def run_query(question, query, params=None):
    if params is None:
        params = []
    print(f"\n{question}")
    try:
        result = pd.read_sql_query(query, conn, params=params)
        if result.empty:
            print("No matching data found.")
        else:
            print(result.to_string(index=False))
        return result
    except Exception as error:
        print(f"Query error: {error}")
        return pd.DataFrame()


P = BIGBASKET_PLATFORM_ID

# ============================================================
# 1. EXECUTIVE
# ============================================================

run_query("KPI 1: What is BigBasket's total revenue?", """
SELECT ROUND(SUM(revenue_inr),2) AS total_revenue
FROM pnl_monthly_safe WHERE platform_id=?
""", [P])

run_query("KPI 2: What is BigBasket's total number of orders?", """
SELECT COUNT(order_id) AS total_orders FROM orders WHERE platform_id=?
""", [P])

run_query("KPI 3: What is BigBasket's AOV?", """
SELECT ROUND(AVG(order_value_inr),2) AS aov_inr
FROM orders WHERE platform_id=?
""", [P])

run_query("KPI 4: What is BigBasket's discount rate?", """
SELECT ROUND(
    SUM(COALESCE(discount_inr,0))*100.0 /
    NULLIF(SUM(COALESCE(order_value_inr,0))+SUM(COALESCE(discount_inr,0)),0),2
) AS discount_rate_percent
FROM orders WHERE platform_id=?
""", [P])

run_query("KPI 5: What is BigBasket's profit margin?", """
SELECT ROUND(SUM(profit_inr)*100.0/NULLIF(SUM(revenue_inr),0),2) AS profit_margin_percent
FROM pnl_monthly_safe WHERE platform_id=?
""", [P])

run_query("Question 1: Which cities are BigBasket's strongest markets?", """
SELECT city, COUNT(order_id) AS total_orders, ROUND(SUM(order_value_inr),2) AS order_value
FROM orders WHERE platform_id=? GROUP BY city
ORDER BY total_orders DESC, order_value DESC
""", [P])

run_query("Question 2: Where is BigBasket losing business?", """
SELECT city, COUNT(order_id) AS total_orders,
ROUND(SUM(CASE WHEN LOWER(TRIM(order_status)) IN ('cancelled','returned') THEN 1 ELSE 0 END)*100.0/COUNT(order_id),2) AS problem_order_rate_percent
FROM orders WHERE platform_id=? GROUP BY city
ORDER BY problem_order_rate_percent DESC
""", [P])

run_query("Question 3: Is growth driven more by customers or order frequency?", """
SELECT strftime('%Y-%m',order_datetime) AS month,
COUNT(order_id) AS orders,
COUNT(DISTINCT customer_id) AS active_customers,
ROUND(COUNT(order_id)*1.0/NULLIF(COUNT(DISTINCT customer_id),0),2) AS orders_per_customer
FROM orders WHERE platform_id=? AND order_datetime IS NOT NULL
GROUP BY strftime('%Y-%m',order_datetime) ORDER BY month
""", [P])

run_query("Question 4: How dependent is BigBasket on discounts?", """
SELECT ROUND(SUM(order_value_inr),2) AS net_order_value,
ROUND(SUM(discount_inr),2) AS total_discount,
ROUND(SUM(discount_inr)*100.0/NULLIF(SUM(order_value_inr)+SUM(discount_inr),0),2) AS discount_rate_percent
FROM orders WHERE platform_id=?
""", [P])

run_query("Question 5: Which cities generate the best profit margins?", """
SELECT city, ROUND(SUM(revenue_inr),2) AS revenue, ROUND(SUM(profit_inr),2) AS profit,
ROUND(SUM(profit_inr)*100.0/NULLIF(SUM(revenue_inr),0),2) AS profit_margin_percent
FROM pnl_monthly_safe WHERE platform_id=? GROUP BY city
ORDER BY profit_margin_percent DESC
""", [P])

# ============================================================
# 2. DARK STORES
# ============================================================

run_query("KPI 1: How many BigBasket stores are there?", """
SELECT COUNT(DISTINCT store_id) AS store_count
FROM orders WHERE platform_id=?
""", [P])

run_query("KPI 2: What are BigBasket's orders per store?", """
SELECT ROUND(COUNT(order_id)*1.0/NULLIF(COUNT(DISTINCT store_id),0),2) AS orders_per_store
FROM orders WHERE platform_id=?
""", [P])

run_query("KPI 3: What is the average BigBasket store size?", """
SELECT ROUND(AVG(sqft_area),2) AS average_store_size_sqft
FROM dark_stores WHERE store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=?)
""", [P])

run_query("KPI 4: What is BigBasket's store productivity?", """
SELECT ROUND(COUNT(o.order_id)*1.0/NULLIF(SUM(ds.sqft_area),0),4) AS orders_per_sqft
FROM dark_stores ds JOIN orders o ON ds.store_id=o.store_id
WHERE o.platform_id=?
""", [P])

run_query("KPI 5: What is each store's BigBasket contribution?", """
SELECT ds.store_id, ds.store_name, ds.city, COUNT(o.order_id) AS orders,
ROUND(SUM(o.order_value_inr),2) AS order_value
FROM dark_stores ds JOIN orders o ON ds.store_id=o.store_id
WHERE o.platform_id=? GROUP BY ds.store_id,ds.store_name,ds.city
ORDER BY order_value DESC
""", [P])

run_query("Question 1: Which BigBasket stores perform best?", """
SELECT ds.store_id,ds.store_name,ds.city,COUNT(o.order_id) AS orders,
ROUND(AVG(o.order_value_inr),2) AS aov
FROM dark_stores ds JOIN orders o ON ds.store_id=o.store_id
WHERE o.platform_id=? GROUP BY ds.store_id,ds.store_name,ds.city
ORDER BY orders DESC,aov DESC
""", [P])

run_query("Question 2: Which stores are underperforming?", """
SELECT ds.store_id,ds.store_name,ds.city,ds.sqft_area,COUNT(o.order_id) AS orders,
ROUND(COUNT(o.order_id)*1.0/NULLIF(ds.sqft_area,0),4) AS orders_per_sqft
FROM dark_stores ds LEFT JOIN orders o ON ds.store_id=o.store_id AND o.platform_id=?
GROUP BY ds.store_id,ds.store_name,ds.city,ds.sqft_area
ORDER BY orders ASC,orders_per_sqft ASC
""", [P])

run_query("Question 3: Which cities need more capacity?", """
SELECT city,COUNT(order_id) AS orders,COUNT(DISTINCT store_id) AS stores,
ROUND(COUNT(order_id)*1.0/NULLIF(COUNT(DISTINCT store_id),0),2) AS orders_per_store
FROM orders WHERE platform_id=? GROUP BY city
ORDER BY orders_per_store DESC,orders DESC
""", [P])

run_query("Question 4: Does larger store size translate into higher order volume?", """
SELECT ds.store_id,ds.store_name,ds.city,ds.sqft_area,COUNT(o.order_id) AS orders
FROM dark_stores ds LEFT JOIN orders o ON ds.store_id=o.store_id AND o.platform_id=?
GROUP BY ds.store_id,ds.store_name,ds.city,ds.sqft_area ORDER BY ds.sqft_area DESC
""", [P])

run_query("Question 5: Which stores are underutilized?", """
SELECT ds.store_id,ds.store_name,ds.city,ds.sqft_area,COUNT(o.order_id) AS orders,
ROUND(COUNT(o.order_id)*1.0/NULLIF(ds.sqft_area,0),4) AS orders_per_sqft
FROM dark_stores ds LEFT JOIN orders o ON ds.store_id=o.store_id AND o.platform_id=?
GROUP BY ds.store_id,ds.store_name,ds.city,ds.sqft_area
ORDER BY orders_per_sqft ASC,ds.sqft_area DESC
""", [P])

# ============================================================
# 3. EMPLOYEES
# ============================================================

run_query("KPI 1: How many employees does BigBasket have?", """
SELECT COUNT(DISTINCT employee_id) AS total_employees FROM employees
WHERE store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
""", [P])

run_query("KPI 2: How many active employees does BigBasket have?", """
SELECT COUNT(DISTINCT employee_id) AS active_employees FROM employees
WHERE LOWER(TRIM(employment_status)) IN ('active','working')
AND store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
""", [P])

run_query("KPI 3: What is BigBasket's average monthly salary?", """
SELECT ROUND(AVG(monthly_salary_inr),2) AS average_monthly_salary FROM employees
WHERE store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
""", [P])

run_query("KPI 4: How many employees are there per store?", """
SELECT ROUND(COUNT(DISTINCT employee_id)*1.0/NULLIF(COUNT(DISTINCT store_id),0),2) AS employees_per_store
FROM employees WHERE store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
""", [P])

run_query("KPI 5: What is employee cost per BigBasket order?", """
SELECT ROUND(
    (SELECT SUM(monthly_salary_inr) FROM employees
     WHERE store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=?)) * 1.0 /
    NULLIF((SELECT COUNT(order_id) FROM orders WHERE platform_id=?),0),2
) AS employee_cost_per_order
""", [P,P])

run_query("Question 1: Which stores have the highest employee count?", """
SELECT e.store_id,ds.store_name,ds.city,COUNT(e.employee_id) AS employee_count
FROM employees e JOIN dark_stores ds ON e.store_id=ds.store_id
WHERE e.store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
GROUP BY e.store_id,ds.store_name,ds.city ORDER BY employee_count DESC
""", [P])

run_query("Question 2: Which stores are understaffed relative to order volume?", """
SELECT ds.store_id,ds.store_name,ds.city,COUNT(DISTINCT e.employee_id) AS employees,
COUNT(DISTINCT o.order_id) AS orders,
ROUND(COUNT(DISTINCT o.order_id)*1.0/NULLIF(COUNT(DISTINCT e.employee_id),0),2) AS orders_per_employee
FROM dark_stores ds LEFT JOIN employees e ON ds.store_id=e.store_id
LEFT JOIN orders o ON ds.store_id=o.store_id AND o.platform_id=?
GROUP BY ds.store_id,ds.store_name,ds.city
ORDER BY orders_per_employee DESC
""", [P])

run_query("Question 3: Which employee roles have the highest cost?", """
SELECT role,COUNT(employee_id) AS employees,ROUND(AVG(monthly_salary_inr),2) AS avg_salary,
ROUND(SUM(monthly_salary_inr),2) AS total_monthly_cost
FROM employees WHERE store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
GROUP BY role ORDER BY total_monthly_cost DESC
""", [P])

run_query("Question 4: Which cities have expensive workforce structures?", """
SELECT ds.city,COUNT(e.employee_id) AS employees,ROUND(SUM(e.monthly_salary_inr),2) AS monthly_employee_cost,
ROUND(AVG(e.monthly_salary_inr),2) AS avg_salary
FROM employees e JOIN dark_stores ds ON e.store_id=ds.store_id
WHERE e.store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
GROUP BY ds.city ORDER BY monthly_employee_cost DESC
""", [P])

run_query("Question 5: Is staffing aligned with order volume?", """
SELECT ds.store_id,ds.store_name,ds.city,COUNT(DISTINCT e.employee_id) AS employees,
COUNT(DISTINCT o.order_id) AS orders,
ROUND(COUNT(DISTINCT o.order_id)*1.0/NULLIF(COUNT(DISTINCT e.employee_id),0),2) AS orders_per_employee
FROM dark_stores ds LEFT JOIN employees e ON ds.store_id=e.store_id
LEFT JOIN orders o ON ds.store_id=o.store_id AND o.platform_id=?
GROUP BY ds.store_id,ds.store_name,ds.city ORDER BY orders DESC
""", [P])

# ============================================================
# 4. PRODUCTS
# ============================================================

run_query("KPI 1: How many products are in BigBasket's catalogue?", """
SELECT COUNT(DISTINCT product_id) AS product_count FROM products
""")
run_query("KPI 2: What is BigBasket's average selling price?", """
SELECT ROUND(AVG(selling_price),2) AS average_selling_price FROM products
""")
run_query("KPI 3: What is BigBasket's average product discount?", """
SELECT ROUND(AVG(discount_percent),2) AS average_discount_percent FROM products
""")
run_query("KPI 4: What is BigBasket's category mix?", """
SELECT category,COUNT(product_id) AS product_count,
ROUND(COUNT(product_id)*100.0/NULLIF((SELECT COUNT(*) FROM products),0),2) AS category_mix_percent
FROM products GROUP BY category ORDER BY product_count DESC
""")
run_query("KPI 5: How many price outliers are there?", """
SELECT COUNT(*) AS price_outlier_count FROM products
WHERE selling_price > (SELECT AVG(selling_price)*2 FROM products)
   OR selling_price < (SELECT AVG(selling_price)*0.5 FROM products)
""")

run_query("Question 1: Which categories dominate BigBasket's catalogue?", """
SELECT category,COUNT(product_id) AS product_count FROM products
GROUP BY category ORDER BY product_count DESC
""")
run_query("Question 2: Which products have the highest discounts?", """
SELECT product_id,product_name,category,ROUND(discount_percent,2) AS discount_percent,
ROUND(mrp,2) AS mrp,ROUND(selling_price,2) AS selling_price
FROM products ORDER BY discount_percent DESC LIMIT 20
""")
run_query("Question 3: Which products have unusually high prices?", """
SELECT product_id,product_name,category,ROUND(selling_price,2) AS selling_price,
ROUND(selling_price/(SELECT AVG(selling_price) FROM products),2) AS price_vs_average
FROM products WHERE selling_price > (SELECT AVG(selling_price)*2 FROM products)
ORDER BY selling_price DESC
""")
run_query("Question 4: Which brands dominate the assortment?", """
SELECT brand,COUNT(product_id) AS product_count,COUNT(DISTINCT category) AS category_count
FROM products GROUP BY brand ORDER BY product_count DESC
""")
run_query("Question 5: Which categories are underrepresented?", """
SELECT category,COUNT(product_id) AS product_count FROM products
GROUP BY category ORDER BY product_count ASC
""")

# ============================================================
# 5. CUSTOMERS
# ============================================================

BB_CUSTOMER = "LOWER(TRIM(signup_platform)) LIKE 'big basket%' OR LOWER(TRIM(signup_platform))='bigbasket'"

run_query("KPI 1: How many BigBasket customers are there?", f"""
SELECT COUNT(DISTINCT customer_id) AS total_customers FROM customers WHERE {BB_CUSTOMER}
""")
run_query("KPI 2: How is BigBasket customer growth changing?", f"""
SELECT strftime('%Y-%m',signup_date) AS month,COUNT(customer_id) AS new_customers
FROM customers WHERE ({BB_CUSTOMER}) AND signup_date IS NOT NULL
GROUP BY strftime('%Y-%m',signup_date) ORDER BY month
""")
run_query("KPI 3: How are BigBasket customers distributed by city?", f"""
SELECT city,COUNT(customer_id) AS customer_count FROM customers
WHERE {BB_CUSTOMER} GROUP BY city ORDER BY customer_count DESC
""")
run_query("KPI 4: What is the signup platform mix?", """
SELECT signup_platform,COUNT(customer_id) AS customers FROM customers
GROUP BY signup_platform ORDER BY customers DESC
""")
run_query("KPI 5: What is BigBasket's app version mix?", f"""
SELECT app_version,COUNT(customer_id) AS customers FROM customers
WHERE {BB_CUSTOMER} GROUP BY app_version ORDER BY customers DESC
""")

run_query("Question 1: Which cities have the largest BigBasket customer base?", f"""
SELECT city,COUNT(customer_id) AS customers FROM customers
WHERE {BB_CUSTOMER} GROUP BY city ORDER BY customers DESC
""")
run_query("Question 2: Which cities are growing fastest?", f"""
SELECT city,strftime('%Y-%m',signup_date) AS month,COUNT(customer_id) AS new_customers
FROM customers WHERE ({BB_CUSTOMER}) AND signup_date IS NOT NULL
GROUP BY city,strftime('%Y-%m',signup_date) ORDER BY month DESC,new_customers DESC
""")
run_query("Question 3: Where is customer acquisition weak?", f"""
SELECT city,COUNT(customer_id) AS customers FROM customers
WHERE {BB_CUSTOMER} GROUP BY city ORDER BY customers ASC
""")
run_query("Question 4: Which signup platforms bring more users?", """
SELECT signup_platform,COUNT(customer_id) AS customers FROM customers
GROUP BY signup_platform ORDER BY customers DESC
""")
run_query("Question 5: Which cities have high customers but low orders?", f"""
SELECT c.city,COUNT(DISTINCT c.customer_id) AS customers,COUNT(DISTINCT o.order_id) AS orders,
ROUND(COUNT(DISTINCT o.order_id)*1.0/NULLIF(COUNT(DISTINCT c.customer_id),0),2) AS orders_per_customer
FROM customers c LEFT JOIN orders o ON c.customer_id=o.customer_id AND o.platform_id=?
WHERE {BB_CUSTOMER} GROUP BY c.city
ORDER BY customers DESC,orders_per_customer ASC
""", [P])

# ============================================================
# 6. ORDERS
# ============================================================

run_query("KPI 1: What is BigBasket's total number of orders?", "SELECT COUNT(order_id) AS total_orders FROM orders WHERE platform_id=?", [P])
run_query("KPI 2: What is BigBasket's AOV?", "SELECT ROUND(AVG(order_value_inr),2) AS aov_inr FROM orders WHERE platform_id=?", [P])
run_query("KPI 3: What is BigBasket's delivery completion rate?", """
SELECT ROUND(SUM(CASE WHEN LOWER(TRIM(order_status))='delivered' THEN 1 ELSE 0 END)*100.0/NULLIF(COUNT(order_id),0),2) AS delivery_completion_rate_percent
FROM orders WHERE platform_id=?
""", [P])
run_query("KPI 4: What is BigBasket's cancellation rate?", """
SELECT ROUND(SUM(CASE WHEN LOWER(TRIM(order_status))='cancelled' THEN 1 ELSE 0 END)*100.0/NULLIF(COUNT(order_id),0),2) AS cancellation_rate_percent
FROM orders WHERE platform_id=?
""", [P])
run_query("KPI 5: What is BigBasket's return rate?", """
SELECT ROUND(SUM(CASE WHEN LOWER(TRIM(order_status))='returned' THEN 1 ELSE 0 END)*100.0/NULLIF(COUNT(order_id),0),2) AS return_rate_percent
FROM orders WHERE platform_id=?
""", [P])

run_query("Question 1: Which cities generate the highest number of BigBasket orders?", """
SELECT city,COUNT(order_id) AS total_orders,ROUND(AVG(order_value_inr),2) AS aov
FROM orders WHERE platform_id=? GROUP BY city ORDER BY total_orders DESC
""", [P])
run_query("Question 2: Which cities have high cancellation rates?", """
SELECT city,COUNT(order_id) AS orders,
ROUND(SUM(CASE WHEN LOWER(TRIM(order_status))='cancelled' THEN 1 ELSE 0 END)*100.0/COUNT(order_id),2) AS cancellation_rate_percent
FROM orders WHERE platform_id=? GROUP BY city ORDER BY cancellation_rate_percent DESC
""", [P])
run_query("Question 3: Which stores generate the most orders?", """
SELECT o.store_id,ds.store_name,o.city,COUNT(o.order_id) AS total_orders
FROM orders o LEFT JOIN dark_stores ds ON o.store_id=ds.store_id
WHERE o.platform_id=? GROUP BY o.store_id,ds.store_name,o.city ORDER BY total_orders DESC
""", [P])
run_query("Question 4: How is BigBasket AOV changing?", """
SELECT strftime('%Y-%m',order_datetime) AS month,COUNT(order_id) AS orders,
ROUND(AVG(order_value_inr),2) AS aov FROM orders
WHERE platform_id=? AND order_datetime IS NOT NULL
GROUP BY strftime('%Y-%m',order_datetime) ORDER BY month
""", [P])
run_query("Question 5: Which payment method is preferred?", """
SELECT payment_mode,COUNT(order_id) AS orders,
ROUND(COUNT(order_id)*100.0/NULLIF((SELECT COUNT(order_id) FROM orders WHERE platform_id=?),0),2) AS order_share_percent
FROM orders WHERE platform_id=? GROUP BY payment_mode ORDER BY orders DESC
""", [P,P])

# ============================================================
# 7. ORDER ITEMS
# ============================================================

run_query("KPI 1: How many units has BigBasket sold?", """
SELECT SUM(oi.quantity) AS units_sold FROM order_items oi JOIN orders o ON oi.order_id=o.order_id WHERE o.platform_id=?
""", [P])
run_query("KPI 2: What is BigBasket's total item value?", """
SELECT ROUND(SUM(oi.line_total_inr),2) AS item_value FROM order_items oi JOIN orders o ON oi.order_id=o.order_id WHERE o.platform_id=?
""", [P])
run_query("KPI 3: What is BigBasket's average item price?", """
SELECT ROUND(AVG(oi.item_price_inr),2) AS average_item_price FROM order_items oi JOIN orders o ON oi.order_id=o.order_id WHERE o.platform_id=?
""", [P])
run_query("KPI 4: What is BigBasket's average basket size?", """
SELECT ROUND(SUM(oi.quantity)*1.0/NULLIF(COUNT(DISTINCT oi.order_id),0),2) AS average_basket_size_units
FROM order_items oi JOIN orders o ON oi.order_id=o.order_id WHERE o.platform_id=?
""", [P])
run_query("KPI 5: What is category contribution to BigBasket item value?", """
SELECT p.category,ROUND(SUM(oi.line_total_inr),2) AS item_value,
ROUND(SUM(oi.line_total_inr)*100.0/NULLIF((SELECT SUM(oi2.line_total_inr) FROM order_items oi2 JOIN orders o2 ON oi2.order_id=o2.order_id WHERE o2.platform_id=?),0),2) AS contribution_percent
FROM order_items oi JOIN orders o ON oi.order_id=o.order_id JOIN products p ON oi.product_id=p.product_id
WHERE o.platform_id=? GROUP BY p.category ORDER BY item_value DESC
""", [P,P])

run_query("Question 1: Which products sell the highest quantities?", """
SELECT p.product_id,p.product_name,p.category,SUM(oi.quantity) AS units_sold
FROM order_items oi JOIN products p ON oi.product_id=p.product_id JOIN orders o ON oi.order_id=o.order_id
WHERE o.platform_id=? GROUP BY p.product_id,p.product_name,p.category ORDER BY units_sold DESC LIMIT 20
""", [P])
run_query("Question 2: Which products generate the most value?", """
SELECT p.product_id,p.product_name,p.category,ROUND(SUM(oi.line_total_inr),2) AS item_value
FROM order_items oi JOIN products p ON oi.product_id=p.product_id JOIN orders o ON oi.order_id=o.order_id
WHERE o.platform_id=? GROUP BY p.product_id,p.product_name,p.category ORDER BY item_value DESC LIMIT 20
""", [P])
run_query("Question 3: Which categories dominate BigBasket baskets?", """
SELECT p.category,SUM(oi.quantity) AS units_sold,ROUND(SUM(oi.line_total_inr),2) AS item_value
FROM order_items oi JOIN products p ON oi.product_id=p.product_id JOIN orders o ON oi.order_id=o.order_id
WHERE o.platform_id=? GROUP BY p.category ORDER BY item_value DESC,units_sold DESC
""", [P])
run_query("Question 4: What is the typical BigBasket basket?", """
SELECT ROUND(AVG(order_units),2) AS average_units_per_order,
ROUND(AVG(distinct_items),2) AS average_distinct_items_per_order
FROM (
    SELECT oi.order_id,SUM(oi.quantity) AS order_units,COUNT(DISTINCT oi.product_id) AS distinct_items
    FROM order_items oi JOIN orders o ON oi.order_id=o.order_id
    WHERE o.platform_id=? GROUP BY oi.order_id
)
""", [P])
run_query("Question 5: Which products are quantity-heavy versus value-heavy?", """
SELECT p.product_name,p.category,SUM(oi.quantity) AS units_sold,
ROUND(SUM(oi.line_total_inr),2) AS item_value,
ROUND(SUM(oi.line_total_inr)/NULLIF(SUM(oi.quantity),0),2) AS average_unit_value
FROM order_items oi JOIN products p ON oi.product_id=p.product_id JOIN orders o ON oi.order_id=o.order_id
WHERE o.platform_id=? GROUP BY p.product_name,p.category ORDER BY units_sold DESC LIMIT 20
""", [P])

# ============================================================
# 8. INVENTORY
# ============================================================

run_query("KPI 1: How many stock units does BigBasket hold?", """
SELECT SUM(stock_units) AS total_stock_units FROM inventory
WHERE store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
""", [P])
run_query("KPI 2: How many low-stock SKUs does BigBasket have?", """
SELECT COUNT(*) AS low_stock_sku_count FROM inventory
WHERE stock_units<reorder_level AND store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
""", [P])
run_query("KPI 3: What is BigBasket's reorder risk?", """
SELECT ROUND(SUM(CASE WHEN stock_units<reorder_level THEN 1 ELSE 0 END)*100.0/NULLIF(COUNT(*),0),2) AS reorder_risk_percent
FROM inventory WHERE store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
""", [P])
run_query("KPI 4: What is BigBasket's expiry risk?", """
SELECT COUNT(*) AS expiry_risk_count FROM inventory
WHERE expiry_date IS NOT NULL AND date(expiry_date)<=date('now','+30 day')
AND store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
""", [P])
run_query("KPI 5: How concentrated is BigBasket inventory?", """
SELECT store_id,SUM(stock_units) AS stock_units,
ROUND(SUM(stock_units)*100.0/NULLIF((SELECT SUM(stock_units) FROM inventory WHERE store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=?)),0),2) AS inventory_share_percent
FROM inventory WHERE store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
GROUP BY store_id ORDER BY inventory_share_percent DESC
""", [P,P])

run_query("Question 1: Which stores have the highest stockout risk?", """
SELECT i.store_id,ds.store_name,ds.city,COUNT(*) AS sku_count,
SUM(CASE WHEN i.stock_units<i.reorder_level THEN 1 ELSE 0 END) AS low_stock_skus
FROM inventory i JOIN dark_stores ds ON i.store_id=ds.store_id
WHERE i.store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
GROUP BY i.store_id,ds.store_name,ds.city ORDER BY low_stock_skus DESC
""", [P])
run_query("Question 2: Which products are below reorder level?", """
SELECT i.product_id,p.product_name,p.category,i.store_id,i.stock_units,i.reorder_level
FROM inventory i JOIN products p ON i.product_id=p.product_id
WHERE i.stock_units<i.reorder_level AND i.store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
ORDER BY (i.reorder_level-i.stock_units) DESC
""", [P])
run_query("Question 3: Which stores are overstocked?", """
SELECT i.store_id,ds.store_name,ds.city,SUM(i.stock_units) AS stock_units,SUM(i.reorder_level) AS reorder_units,
ROUND(SUM(i.stock_units)*1.0/NULLIF(SUM(i.reorder_level),0),2) AS stock_to_reorder_ratio
FROM inventory i JOIN dark_stores ds ON i.store_id=ds.store_id
WHERE i.store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
GROUP BY i.store_id,ds.store_name,ds.city HAVING stock_to_reorder_ratio>2
ORDER BY stock_to_reorder_ratio DESC
""", [P])
run_query("Question 4: Which products are close to expiry?", """
SELECT i.product_id,p.product_name,p.category,i.store_id,i.stock_units,i.expiry_date
FROM inventory i JOIN products p ON i.product_id=p.product_id
WHERE i.expiry_date IS NOT NULL AND date(i.expiry_date)<=date('now','+30 day')
AND i.store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
ORDER BY i.expiry_date ASC
""", [P])
run_query("Question 5: Which products need urgent replenishment?", """
SELECT i.product_id,p.product_name,p.category,
SUM(i.reorder_level-i.stock_units) AS replenishment_gap
FROM inventory i JOIN products p ON i.product_id=p.product_id
WHERE i.stock_units<i.reorder_level AND i.store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
GROUP BY i.product_id,p.product_name,p.category ORDER BY replenishment_gap DESC
""", [P])

# ============================================================
# 9. LOGISTICS
# ============================================================

run_query("KPI 1: What is BigBasket's delay rate?", """
SELECT ROUND(SUM(CASE WHEN LOWER(TRIM(l.delay_flag))='yes' THEN 1 ELSE 0 END)*100.0/NULLIF(COUNT(l.delivery_id),0),2) AS delay_rate_percent
FROM logistics l JOIN orders o ON l.order_id=o.order_id WHERE o.platform_id=?
""", [P])
run_query("KPI 2: What is BigBasket's average delivery distance?", """
SELECT ROUND(AVG(l.distance_km),2) AS average_delivery_distance_km
FROM logistics l JOIN orders o ON l.order_id=o.order_id WHERE o.platform_id=?
""", [P])
run_query("KPI 3: What is BigBasket's average delivery rating?", """
SELECT ROUND(AVG(l.delivery_rating),2) AS average_delivery_rating
FROM logistics l JOIN orders o ON l.order_id=o.order_id WHERE o.platform_id=?
""", [P])
run_query("KPI 4: How many BigBasket deliveries were delayed?", """
SELECT COUNT(l.delivery_id) AS delayed_deliveries FROM logistics l JOIN orders o ON l.order_id=o.order_id
WHERE o.platform_id=? AND LOWER(TRIM(l.delay_flag))='yes'
""", [P])
run_query("KPI 5: What is BigBasket's vehicle mix?", """
SELECT l.vehicle_type,COUNT(l.delivery_id) AS deliveries,
ROUND(COUNT(l.delivery_id)*100.0/NULLIF((SELECT COUNT(l2.delivery_id) FROM logistics l2 JOIN orders o2 ON l2.order_id=o2.order_id WHERE o2.platform_id=?),0),2) AS vehicle_share_percent
FROM logistics l JOIN orders o ON l.order_id=o.order_id WHERE o.platform_id=?
GROUP BY l.vehicle_type ORDER BY deliveries DESC
""", [P,P])

run_query("Question 1: Which cities have the highest delays?", """
SELECT o.city,COUNT(l.delivery_id) AS deliveries,
ROUND(SUM(CASE WHEN LOWER(TRIM(l.delay_flag))='yes' THEN 1 ELSE 0 END)*100.0/NULLIF(COUNT(l.delivery_id),0),2) AS delay_rate_percent
FROM logistics l JOIN orders o ON l.order_id=o.order_id WHERE o.platform_id=?
GROUP BY o.city ORDER BY delay_rate_percent DESC
""", [P])
run_query("Question 2: Which vehicle types perform best?", """
SELECT l.vehicle_type,COUNT(l.delivery_id) AS deliveries,
ROUND(SUM(CASE WHEN LOWER(TRIM(l.delay_flag))='yes' THEN 1 ELSE 0 END)*100.0/NULLIF(COUNT(l.delivery_id),0),2) AS delay_rate_percent,
ROUND(AVG(l.delivery_rating),2) AS average_rating
FROM logistics l JOIN orders o ON l.order_id=o.order_id WHERE o.platform_id=?
GROUP BY l.vehicle_type ORDER BY delay_rate_percent ASC,average_rating DESC
""", [P])
run_query("Question 3: Does distance influence delay?", """
SELECT CASE WHEN distance_km<2 THEN '0-2 km' WHEN distance_km<5 THEN '2-5 km' WHEN distance_km<10 THEN '5-10 km' ELSE '10+ km' END AS distance_band,
COUNT(l.delivery_id) AS deliveries,
ROUND(SUM(CASE WHEN LOWER(TRIM(l.delay_flag))='yes' THEN 1 ELSE 0 END)*100.0/NULLIF(COUNT(l.delivery_id),0),2) AS delay_rate_percent
FROM logistics l JOIN orders o ON l.order_id=o.order_id WHERE o.platform_id=?
GROUP BY distance_band ORDER BY MIN(distance_km)
""", [P])
run_query("Question 4: Which cities receive poor ratings?", """
SELECT o.city,COUNT(l.delivery_id) AS deliveries,ROUND(AVG(l.delivery_rating),2) AS average_rating
FROM logistics l JOIN orders o ON l.order_id=o.order_id WHERE o.platform_id=?
GROUP BY o.city ORDER BY average_rating ASC
""", [P])
run_query("Question 5: Where should BigBasket optimize delivery operations?", """
SELECT o.city,l.vehicle_type,COUNT(l.delivery_id) AS deliveries,
ROUND(SUM(CASE WHEN LOWER(TRIM(l.delay_flag))='yes' THEN 1 ELSE 0 END)*100.0/NULLIF(COUNT(l.delivery_id),0),2) AS delay_rate_percent,
ROUND(AVG(l.delivery_rating),2) AS average_rating
FROM logistics l JOIN orders o ON l.order_id=o.order_id WHERE o.platform_id=?
GROUP BY o.city,l.vehicle_type ORDER BY delay_rate_percent DESC,average_rating ASC
""", [P])

# ============================================================
# 10. MONTHLY P&L
# ============================================================

run_query("KPI 1: What is BigBasket's total P&L revenue?", "SELECT ROUND(SUM(revenue_inr),2) AS revenue FROM pnl_monthly_safe WHERE platform_id=?", [P])
run_query("KPI 2: What is BigBasket's total COGS?", "SELECT ROUND(SUM(cogs_inr),2) AS cogs FROM pnl_monthly_safe WHERE platform_id=?", [P])
run_query("KPI 3: What is BigBasket's total operating expense?", """
SELECT ROUND(SUM(delivery_cost_inr)+SUM(marketing_spend_inr)+SUM(employee_cost_inr)+SUM(other_opex_inr),2) AS operating_expense
FROM pnl_monthly_safe WHERE platform_id=?
""", [P])
run_query("KPI 4: What is BigBasket's total profit?", "SELECT ROUND(SUM(profit_inr),2) AS profit FROM pnl_monthly_safe WHERE platform_id=?", [P])
run_query("KPI 5: What is BigBasket's profit margin?", """
SELECT ROUND(SUM(profit_inr)*100.0/NULLIF(SUM(revenue_inr),0),2) AS profit_margin_percent
FROM pnl_monthly_safe WHERE platform_id=?
""", [P])

run_query("Question 1: Which cities generate the most revenue?", """
SELECT city,ROUND(SUM(revenue_inr),2) AS revenue FROM pnl_monthly_safe
WHERE platform_id=? GROUP BY city ORDER BY revenue DESC
""", [P])
run_query("Question 2: Which cities produce the highest profit margins?", """
SELECT city,ROUND(SUM(revenue_inr),2) AS revenue,ROUND(SUM(profit_inr),2) AS profit,
ROUND(SUM(profit_inr)*100.0/NULLIF(SUM(revenue_inr),0),2) AS profit_margin_percent
FROM pnl_monthly_safe WHERE platform_id=? GROUP BY city ORDER BY profit_margin_percent DESC
""", [P])
run_query("Question 3: Which cities are loss-making?", """
SELECT city,ROUND(SUM(revenue_inr),2) AS revenue,ROUND(SUM(profit_inr),2) AS profit,
ROUND(SUM(profit_inr)*100.0/NULLIF(SUM(revenue_inr),0),2) AS profit_margin_percent
FROM pnl_monthly_safe WHERE platform_id=? GROUP BY city HAVING profit<0 ORDER BY profit ASC
""", [P])
run_query("Question 4: Which costs hurt profitability most?", """
SELECT ROUND(SUM(cogs_inr),2) AS cogs,ROUND(SUM(delivery_cost_inr),2) AS delivery_cost,
ROUND(SUM(marketing_spend_inr),2) AS marketing_spend,ROUND(SUM(employee_cost_inr),2) AS employee_cost,
ROUND(SUM(other_opex_inr),2) AS other_opex
FROM pnl_monthly_safe WHERE platform_id=?
""", [P])
run_query("Question 5: How is monthly profit changing?", """
SELECT month,ROUND(SUM(revenue_inr),2) AS revenue,ROUND(SUM(profit_inr),2) AS profit,
ROUND(SUM(profit_inr)*100.0/NULLIF(SUM(revenue_inr),0),2) AS profit_margin_percent
FROM pnl_monthly_safe WHERE platform_id=? GROUP BY month ORDER BY month
""", [P])

