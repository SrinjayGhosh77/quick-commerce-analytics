import sqlite3
from pathlib import Path
import pandas as pd

# ============================================================
# 1. FIND PROJECT FOLDER
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent

# The script is inside Analysis/, while cleaned data/ and database/
# are one level above it. The extra checks make the code work even
# if the script is moved to the project root later.
PROJECT_DIR = None

possible_folders = [
    SCRIPT_DIR,
    SCRIPT_DIR.parent,
    SCRIPT_DIR.parent.parent,
    Path.cwd(),
    Path.cwd().parent,
]

for folder in possible_folders:
    if (folder / "cleaned data").is_dir():
        PROJECT_DIR = folder
        break

if PROJECT_DIR is None:
    raise FileNotFoundError(
        "Could not find the 'cleaned data' folder. "
        "Place this script inside the project folder or its Analysis folder."
    )

CLEANED_FOLDER = PROJECT_DIR / "cleaned data"
DATABASE_FOLDER = PROJECT_DIR / "database"
DATABASE_FOLDER.mkdir(exist_ok=True)

DATABASE_PATH = DATABASE_FOLDER / "quick_commerce.db"

# ============================================================
# 2. CONNECT TO SQLITE
# ============================================================

conn = sqlite3.connect(DATABASE_PATH)
print("SQLite database connected successfully.")
print(f"Project folder: {PROJECT_DIR}")

# ============================================================
# 3. LOAD CLEANED CSV FILES INTO SQLITE
# ============================================================

files = {
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

for table_name, file_name in files.items():
    file_path = CLEANED_FOLDER / file_name

    if not file_path.exists():
        conn.close()
        raise FileNotFoundError(f"File not found: {file_path}")

    df = pd.read_csv(file_path)

    # Keep platform_id numeric.
    if "platform_id" in df.columns:
        df["platform_id"] = pd.to_numeric(
            df["platform_id"], errors="coerce"
        )

    # Keep important ID columns numeric where available.
    for column in [
        "store_id",
        "employee_id",
        "product_id",
        "customer_id",
        "order_id",
        "order_item_id",
        "inventory_id",
        "delivery_id",
        "pnl_id",
    ]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    # Numeric columns used in calculations.
    numeric_columns = [
        "sqft_area",
        "monthly_salary_inr",
        "mrp",
        "selling_price",
        "discount_percent",
        "quantity",
        "item_price_inr",
        "line_total_inr",
        "stock_units",
        "reorder_level",
        "distance_km",
        "delivery_rating",
        "order_value_inr",
        "discount_inr",
        "promised_delivery_min",
        "actual_delivery_min",
        "revenue_inr",
        "cogs_inr",
        "delivery_cost_inr",
        "marketing_spend_inr",
        "employee_cost_inr",
        "other_opex_inr",
        "orders_count",
    ]

    for column in numeric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    # Create simple standardized columns needed by SQL queries.
    if table_name == "dark_stores":
        if "city_clean" not in df.columns:
            df["city_clean"] = df["city"] if "city" in df.columns else "Unknown"

        if "store_name_clean" not in df.columns and "store_name" in df.columns:
            df["store_name_clean"] = df["store_name"]

    if table_name == "employees":
        if "work_status" not in df.columns:
            if "employment_status" in df.columns:
                status = df["employment_status"].astype("string").str.strip().str.lower()
                df["work_status"] = status.map({
                    "active": "Currently Working",
                    "working": "Currently Working",
                    "on leave": "On Leave",
                    "resigned": "Not Working",
                    "terminated": "Not Working",
                }).fillna("Unknown")
            else:
                df["work_status"] = "Unknown"

    df.to_sql(table_name, conn, if_exists="replace", index=False)

# ============================================================
# 4. FIND ZEPTO PLATFORM ID
# ============================================================

zepto_result = pd.read_sql_query(
    """
    SELECT platform_id
    FROM platforms
    WHERE LOWER(TRIM(platform_name)) = 'zepto'
    LIMIT 1
    """,
    conn,
)

if zepto_result.empty:
    conn.close()
    raise ValueError("Zepto was not found in the platforms table.")

zepto_platform_id = int(zepto_result.iloc[0]["platform_id"])
print(f"Zepto platform_id: {zepto_platform_id}")

# ============================================================
# 5. CREATE SAFE P&L VIEW
# ============================================================

# Missing cost values should not turn the complete profit calculation
# into NULL. COALESCE converts missing costs to zero for analysis.
conn.execute("DROP VIEW IF EXISTS pnl_monthly_safe")
conn.execute(
    """
    CREATE VIEW pnl_monthly_safe AS
    SELECT
        pnl_id,
        platform_id,
        city,
        month,
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
    """
)
conn.commit()

# ============================================================
# 6. REUSABLE FUNCTION
# ============================================================

def run_query(question, query, params=None):
    """Run SQL, show the answer, and return the result DataFrame."""

    if params is None:
        params = []

    print("\n" + question)

    try:
        result = pd.read_sql_query(query, conn, params=params)
    except Exception as error:
        print(f"Query error: {error}")
        return pd.DataFrame()

    if result.empty:
        print("No matching data found.")
    else:
        print(result.to_string(index=False))

    return result

# ============================================================
# 1. ZEPTO — PLATFORM / EXECUTIVE
# ============================================================

run_query(
    "KPI 1: Total Orders",
    """
    SELECT COUNT(*) AS total_orders
    FROM orders
    WHERE platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 2: Total Revenue",
    """
    SELECT ROUND(SUM(order_value_inr), 2) AS total_revenue
    FROM orders
    WHERE platform_id = ?
      AND order_value_inr IS NOT NULL
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 3: Average Order Value (AOV)",
    """
    SELECT ROUND(AVG(order_value_inr), 2) AS average_order_value
    FROM orders
    WHERE platform_id = ?
      AND order_value_inr IS NOT NULL
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 4: Discount Rate",
    """
    SELECT ROUND(
        SUM(COALESCE(discount_inr, 0)) * 100.0
        / NULLIF(SUM(COALESCE(order_value_inr, 0)), 0),
        2
    ) AS discount_rate_percent
    FROM orders
    WHERE platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 5: Profit Margin",
    """
    SELECT ROUND(
        SUM(profit_inr) * 100.0
        / NULLIF(SUM(revenue_inr), 0),
        2
    ) AS profit_margin_percent
    FROM pnl_monthly_safe
    WHERE platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "Question 1: How is Zepto performing overall compared with the other platforms?",
    """
    SELECT
        p.platform_name,
        COUNT(o.order_id) AS total_orders,
        ROUND(SUM(COALESCE(o.order_value_inr, 0)), 2) AS total_revenue,
        ROUND(AVG(o.order_value_inr), 2) AS average_order_value,
        CASE
            WHEN p.platform_id = ? THEN 'Zepto'
            ELSE 'Other Platform'
        END AS comparison_group
    FROM platforms p
    LEFT JOIN orders o
        ON p.platform_id = o.platform_id
    GROUP BY p.platform_id, p.platform_name
    ORDER BY total_revenue DESC
    """,
    [zepto_platform_id],
)

run_query(
    "Question 2: Is Zepto's business growing or declining over time?",
    """
    SELECT
        SUBSTR(order_datetime, 1, 4) AS year,
        COUNT(*) AS orders,
        ROUND(SUM(COALESCE(order_value_inr, 0)), 2) AS revenue
    FROM orders
    WHERE platform_id = ?
    GROUP BY SUBSTR(order_datetime, 1, 4)
    ORDER BY year
    """,
    [zepto_platform_id],
)

run_query(
    "Question 3: Which cities contribute the most to Zepto's business?",
    """
    SELECT
        ds.city,
        COUNT(o.order_id) AS orders,
        ROUND(SUM(COALESCE(o.order_value_inr, 0)), 2) AS revenue
    FROM orders o
    JOIN dark_stores ds
        ON o.store_id = ds.store_id
    WHERE o.platform_id = ?
    GROUP BY ds.city
    ORDER BY revenue DESC
    """,
    [zepto_platform_id],
)

run_query(
    "Question 4: Is Zepto relying heavily on discounts to generate orders?",
    """
    SELECT
        COUNT(*) AS orders,
        ROUND(SUM(COALESCE(discount_inr, 0)), 2) AS total_discount,
        ROUND(SUM(COALESCE(order_value_inr, 0)), 2) AS total_order_value,
        ROUND(
            SUM(COALESCE(discount_inr, 0)) * 100.0
            / NULLIF(SUM(COALESCE(order_value_inr, 0)), 0),
            2
        ) AS discount_rate_percent,
        CASE
            WHEN SUM(COALESCE(discount_inr, 0)) * 100.0
                 / NULLIF(SUM(COALESCE(order_value_inr, 0)), 0) >= 15
            THEN 'High Discount Dependence'
            WHEN SUM(COALESCE(discount_inr, 0)) * 100.0
                 / NULLIF(SUM(COALESCE(order_value_inr, 0)), 0) >= 5
            THEN 'Moderate Discount Dependence'
            ELSE 'Low Discount Dependence'
        END AS discount_status
    FROM orders
    WHERE platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "Question 5: Is Zepto's profitability improving or declining over time?",
    """
    SELECT
        month,
        ROUND(SUM(revenue_inr), 2) AS revenue,
        ROUND(SUM(profit_inr), 2) AS profit,
        ROUND(
            SUM(profit_inr) * 100.0
            / NULLIF(SUM(revenue_inr), 0),
            2
        ) AS profit_margin_percent
    FROM pnl_monthly_safe
    WHERE platform_id = ?
    GROUP BY month
    ORDER BY month
    """,
    [zepto_platform_id],
)

# ============================================================
# 2. ZEPTO — STORE
# ============================================================

run_query(
    "KPI 1: Number of Dark Stores",
    """
    SELECT COUNT(*) AS dark_store_count
    FROM dark_stores
    WHERE platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 2: Orders per Store",
    """
    SELECT ROUND(
        (SELECT COUNT(*) FROM orders WHERE platform_id = ?) * 1.0
        / NULLIF((SELECT COUNT(*) FROM dark_stores WHERE platform_id = ?), 0),
        2
    ) AS orders_per_store
    """,
    [zepto_platform_id, zepto_platform_id],
)

run_query(
    "KPI 3: Average Store Size (sqft)",
    """
    SELECT ROUND(AVG(sqft_area), 2) AS average_store_size_sqft
    FROM dark_stores
    WHERE platform_id = ?
      AND sqft_area IS NOT NULL
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 4: Orders per Sqft",
    """
    SELECT ROUND(
        (SELECT COUNT(*) FROM orders WHERE platform_id = ?) * 1.0
        / NULLIF(
            (SELECT SUM(sqft_area)
             FROM dark_stores
             WHERE platform_id = ?
               AND sqft_area IS NOT NULL),
            0
        ),
        4
    ) AS orders_per_sqft
    """,
    [zepto_platform_id, zepto_platform_id],
)

run_query(
    "KPI 5: Store Revenue Contribution",
    """
    WITH store_revenue AS (
        SELECT
            ds.store_id,
            SUM(COALESCE(o.order_value_inr, 0)) AS revenue
        FROM dark_stores ds
        LEFT JOIN orders o
            ON ds.store_id = o.store_id
           AND o.platform_id = ?
        WHERE ds.platform_id = ?
        GROUP BY ds.store_id
    ), total_revenue AS (
        SELECT SUM(revenue) AS revenue
        FROM store_revenue
    )
    SELECT ROUND(
        MAX(sr.revenue) * 100.0 / NULLIF(tr.revenue, 0),
        2
    ) AS top_store_revenue_contribution_percent
    FROM store_revenue sr
    CROSS JOIN total_revenue tr
    """,
    [zepto_platform_id, zepto_platform_id],
)

run_query(
    "Question 1: Which Zepto stores generate the highest number of orders?",
    """
    SELECT
        ds.store_id,
        COALESCE(ds.store_name_clean, ds.store_name) AS store_name,
        ds.city,
        COUNT(o.order_id) AS orders
    FROM dark_stores ds
    LEFT JOIN orders o
        ON ds.store_id = o.store_id
       AND o.platform_id = ?
    WHERE ds.platform_id = ?
    GROUP BY ds.store_id, store_name, ds.city
    ORDER BY orders DESC
    LIMIT 15
    """,
    [zepto_platform_id, zepto_platform_id],
)

run_query(
    "Question 2: Which stores are underutilized?",
    """
    SELECT
        ds.store_id,
        COALESCE(ds.store_name_clean, ds.store_name) AS store_name,
        ds.city,
        COALESCE(ds.sqft_area, 0) AS sqft_area,
        COUNT(o.order_id) AS orders
    FROM dark_stores ds
    LEFT JOIN orders o
        ON ds.store_id = o.store_id
       AND o.platform_id = ?
    WHERE ds.platform_id = ?
    GROUP BY ds.store_id, store_name, ds.city, ds.sqft_area
    ORDER BY orders ASC, sqft_area DESC
    LIMIT 15
    """,
    [zepto_platform_id, zepto_platform_id],
)

run_query(
    "Question 3: Which cities have the highest concentration of Zepto stores?",
    """
    SELECT
        city,
        COUNT(*) AS dark_stores
    FROM dark_stores
    WHERE platform_id = ?
    GROUP BY city
    ORDER BY dark_stores DESC
    """,
    [zepto_platform_id],
)

run_query(
    "Question 4: Which stores generate high orders with a relatively small footprint?",
    """
    SELECT
        ds.store_id,
        COALESCE(ds.store_name_clean, ds.store_name) AS store_name,
        ds.city,
        ROUND(ds.sqft_area, 2) AS sqft_area,
        COUNT(o.order_id) AS orders,
        ROUND(
            COUNT(o.order_id) * 1.0 / NULLIF(ds.sqft_area, 0),
            4
        ) AS orders_per_sqft
    FROM dark_stores ds
    LEFT JOIN orders o
        ON ds.store_id = o.store_id
       AND o.platform_id = ?
    WHERE ds.platform_id = ?
      AND ds.sqft_area IS NOT NULL
    GROUP BY ds.store_id, store_name, ds.city, ds.sqft_area
    ORDER BY orders_per_sqft DESC
    LIMIT 15
    """,
    [zepto_platform_id, zepto_platform_id],
)

run_query(
    "Question 5: Which Zepto stores are the biggest operational opportunities?",
    """
    SELECT
        ds.store_id,
        COALESCE(ds.store_name_clean, ds.store_name) AS store_name,
        ds.city,
        ROUND(ds.sqft_area, 2) AS sqft_area,
        COUNT(o.order_id) AS orders,
        ROUND(SUM(COALESCE(o.order_value_inr, 0)), 2) AS revenue,
        CASE
            WHEN COUNT(o.order_id) = 0 THEN 'Immediate Attention'
            WHEN COUNT(o.order_id) * 1.0 / NULLIF(ds.sqft_area, 0) < 0.50
                THEN 'Underutilized'
            WHEN COUNT(o.order_id) * 1.0 / NULLIF(ds.sqft_area, 0) < 1.00
                THEN 'Optimization Opportunity'
            ELSE 'Strong Performer'
        END AS operational_status
    FROM dark_stores ds
    LEFT JOIN orders o
        ON ds.store_id = o.store_id
       AND o.platform_id = ?
    WHERE ds.platform_id = ?
    GROUP BY ds.store_id, store_name, ds.city, ds.sqft_area
    ORDER BY orders ASC
    LIMIT 20
    """,
    [zepto_platform_id, zepto_platform_id],
)

# ============================================================
# 3. ZEPTO — EMPLOYEE
# ============================================================

run_query(
    "KPI 1: Total Employees",
    """
    SELECT COUNT(*) AS total_employees
    FROM employees e
    JOIN dark_stores ds
        ON e.store_id = ds.store_id
    WHERE ds.platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 2: Currently Working Employees",
    """
    SELECT COUNT(*) AS currently_working_employees
    FROM employees e
    JOIN dark_stores ds
        ON e.store_id = ds.store_id
    WHERE ds.platform_id = ?
      AND e.work_status = 'Currently Working'
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 3: Average Monthly Salary",
    """
    SELECT ROUND(AVG(e.monthly_salary_inr), 2) AS average_monthly_salary
    FROM employees e
    JOIN dark_stores ds
        ON e.store_id = ds.store_id
    WHERE ds.platform_id = ?
      AND e.monthly_salary_inr IS NOT NULL
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 4: Employees per Store",
    """
    SELECT ROUND(
        COUNT(e.employee_id) * 1.0
        / NULLIF(COUNT(DISTINCT ds.store_id), 0),
        2
    ) AS employees_per_store
    FROM dark_stores ds
    LEFT JOIN employees e
        ON ds.store_id = e.store_id
    WHERE ds.platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 5: Employee Cost per Order",
    """
    SELECT ROUND(
        (SELECT SUM(COALESCE(e.monthly_salary_inr, 0))
         FROM employees e
         JOIN dark_stores ds
             ON e.store_id = ds.store_id
         WHERE ds.platform_id = ?
           AND e.work_status = 'Currently Working')
        / NULLIF(
            (SELECT COUNT(*)
             FROM orders
             WHERE platform_id = ?),
            0
        ),
        2
    ) AS employee_cost_per_order
    """,
    [zepto_platform_id, zepto_platform_id],
)

run_query(
    "Question 1: Which Zepto stores have the largest employee workforce?",
    """
    SELECT
        ds.store_id,
        ds.city,
        COUNT(e.employee_id) AS employees
    FROM dark_stores ds
    LEFT JOIN employees e
        ON ds.store_id = e.store_id
    WHERE ds.platform_id = ?
    GROUP BY ds.store_id, ds.city
    ORDER BY employees DESC
    LIMIT 15
    """,
    [zepto_platform_id],
)

run_query(
    "Question 2: Which stores have too few employees relative to their order volume?",
    """
    WITH store_orders AS (
        SELECT
            store_id,
            COUNT(*) AS orders
        FROM orders
        WHERE platform_id = ?
        GROUP BY store_id
    ), store_employees AS (
        SELECT
            e.store_id,
            COUNT(*) AS employees
        FROM employees e
        JOIN dark_stores ds
            ON e.store_id = ds.store_id
        WHERE ds.platform_id = ?
          AND e.work_status = 'Currently Working'
        GROUP BY e.store_id
    )
    SELECT
        ds.store_id,
        ds.city,
        COALESCE(so.orders, 0) AS orders,
        COALESCE(se.employees, 0) AS employees,
        ROUND(
            COALESCE(so.orders, 0) * 1.0
            / NULLIF(COALESCE(se.employees, 0), 0),
            2
        ) AS orders_per_employee
    FROM dark_stores ds
    LEFT JOIN store_orders so
        ON ds.store_id = so.store_id
    LEFT JOIN store_employees se
        ON ds.store_id = se.store_id
    WHERE ds.platform_id = ?
      AND COALESCE(so.orders, 0) > 0
    ORDER BY orders_per_employee DESC
    LIMIT 15
    """,
    [zepto_platform_id, zepto_platform_id, zepto_platform_id],
)

run_query(
    "Question 3: Which roles have the highest salary cost?",
    """
    SELECT
        e.role,
        COUNT(*) AS employees,
        ROUND(SUM(COALESCE(e.monthly_salary_inr, 0)), 2) AS salary_cost
    FROM employees e
    JOIN dark_stores ds
        ON e.store_id = ds.store_id
    WHERE ds.platform_id = ?
    GROUP BY e.role
    ORDER BY salary_cost DESC
    """,
    [zepto_platform_id],
)

run_query(
    "Question 4: Which cities have the highest workforce cost?",
    """
    SELECT
        ds.city,
        COUNT(e.employee_id) AS employees,
        ROUND(SUM(COALESCE(e.monthly_salary_inr, 0)), 2) AS workforce_cost
    FROM employees e
    JOIN dark_stores ds
        ON e.store_id = ds.store_id
    WHERE ds.platform_id = ?
    GROUP BY ds.city
    ORDER BY workforce_cost DESC
    """,
    [zepto_platform_id],
)

run_query(
    "Question 5: How does employee productivity vary across Zepto cities?",
    """
    WITH city_employees AS (
        SELECT
            ds.city,
            COUNT(e.employee_id) AS employees
        FROM employees e
        JOIN dark_stores ds
            ON e.store_id = ds.store_id
        WHERE ds.platform_id = ?
          AND e.work_status = 'Currently Working'
        GROUP BY ds.city
    ), city_orders AS (
        SELECT
            ds.city,
            COUNT(o.order_id) AS orders
        FROM orders o
        JOIN dark_stores ds
            ON o.store_id = ds.store_id
        WHERE o.platform_id = ?
        GROUP BY ds.city
    )
    SELECT
        ce.city,
        ce.employees,
        COALESCE(co.orders, 0) AS orders,
        ROUND(
            COALESCE(co.orders, 0) * 1.0 / NULLIF(ce.employees, 0),
            2
        ) AS orders_per_employee
    FROM city_employees ce
    LEFT JOIN city_orders co
        ON ce.city = co.city
    ORDER BY orders_per_employee DESC
    """,
    [zepto_platform_id, zepto_platform_id],
)

# ============================================================
# 4. ZEPTO — PRODUCT
# ============================================================

# Products do not contain platform_id, so Zepto-specific product
# analysis is based on products actually purchased through Zepto.

run_query(
    "KPI 1: Number of Products",
    """
    SELECT COUNT(DISTINCT oi.product_id) AS number_of_products
    FROM order_items oi
    JOIN orders o
        ON oi.order_id = o.order_id
    WHERE o.platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 2: Average Selling Price",
    """
    SELECT ROUND(AVG(p.selling_price), 2) AS average_selling_price
    FROM products p
    JOIN (
        SELECT DISTINCT oi.product_id
        FROM order_items oi
        JOIN orders o
            ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
    ) z
        ON p.product_id = z.product_id
    WHERE p.selling_price IS NOT NULL
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 3: Average Discount %",
    """
    SELECT ROUND(AVG(p.discount_percent), 2) AS average_discount_percent
    FROM products p
    JOIN (
        SELECT DISTINCT oi.product_id
        FROM order_items oi
        JOIN orders o
            ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
    ) z
        ON p.product_id = z.product_id
    WHERE p.discount_percent IS NOT NULL
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 4: Product Category Count",
    """
    SELECT COUNT(DISTINCT p.category) AS product_category_count
    FROM products p
    JOIN (
        SELECT DISTINCT oi.product_id
        FROM order_items oi
        JOIN orders o
            ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
    ) z
        ON p.product_id = z.product_id
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 5: Outlier Product Count",
    """
    SELECT COUNT(*) AS outlier_product_count
    FROM products p
    JOIN (
        SELECT DISTINCT oi.product_id
        FROM order_items oi
        JOIN orders o
            ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
    ) z
        ON p.product_id = z.product_id
    WHERE p.price_status = 'Outlier'
    """,
    [zepto_platform_id],
)

run_query(
    "Question 1: Which product categories are most important for Zepto?",
    """
    SELECT
        p.category,
        SUM(COALESCE(oi.quantity, 0)) AS units_sold,
        ROUND(SUM(COALESCE(oi.line_total_inr, 0)), 2) AS item_revenue
    FROM order_items oi
    JOIN orders o
        ON oi.order_id = o.order_id
    JOIN products p
        ON oi.product_id = p.product_id
    WHERE o.platform_id = ?
    GROUP BY p.category
    ORDER BY item_revenue DESC
    """,
    [zepto_platform_id],
)

run_query(
    "Question 2: Which products contribute the most item revenue?",
    """
    SELECT
        p.product_id,
        p.product_name,
        p.category,
        SUM(COALESCE(oi.quantity, 0)) AS units_sold,
        ROUND(SUM(COALESCE(oi.line_total_inr, 0)), 2) AS item_revenue
    FROM order_items oi
    JOIN orders o
        ON oi.order_id = o.order_id
    JOIN products p
        ON oi.product_id = p.product_id
    WHERE o.platform_id = ?
    GROUP BY p.product_id, p.product_name, p.category
    ORDER BY item_revenue DESC
    LIMIT 15
    """,
    [zepto_platform_id],
)

run_query(
    "Question 3: Which categories receive the deepest discounts?",
    """
    SELECT
        p.category,
        ROUND(AVG(p.discount_percent), 2) AS average_discount_percent,
        COUNT(DISTINCT p.product_id) AS products
    FROM products p
    JOIN (
        SELECT DISTINCT oi.product_id
        FROM order_items oi
        JOIN orders o
            ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
    ) z
        ON p.product_id = z.product_id
    GROUP BY p.category
    ORDER BY average_discount_percent DESC
    """,
    [zepto_platform_id],
)

run_query(
    "Question 4: Which brands dominate Zepto's catalogue?",
    """
    SELECT
        COALESCE(p.brand, 'Unknown') AS brand,
        COUNT(DISTINCT p.product_id) AS products,
        SUM(COALESCE(oi.quantity, 0)) AS units_sold,
        ROUND(SUM(COALESCE(oi.line_total_inr, 0)), 2) AS item_revenue
    FROM products p
    JOIN order_items oi
        ON p.product_id = oi.product_id
    JOIN orders o
        ON oi.order_id = o.order_id
    WHERE o.platform_id = ?
    GROUP BY COALESCE(p.brand, 'Unknown')
    ORDER BY products DESC, item_revenue DESC
    LIMIT 15
    """,
    [zepto_platform_id],
)


# ============================================================
# 5. ZEPTO — CUSTOMER
# ============================================================

run_query(
    "KPI 1: Total Customers",
    """
    SELECT COUNT(DISTINCT customer_id) AS total_customers
    FROM orders
    WHERE platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 2: Customer Acquisition",
    """
    SELECT COUNT(DISTINCT customer_id) AS customer_acquisition
    FROM customers
    WHERE LOWER(TRIM(signup_platform)) = 'zepto'
    """,
)

run_query(
    "KPI 3: Customers by City",
    """
    SELECT
        c.city,
        COUNT(DISTINCT c.customer_id) AS customers
    FROM customers c
    JOIN (
        SELECT DISTINCT customer_id
        FROM orders
        WHERE platform_id = ?
    ) z
        ON c.customer_id = z.customer_id
    GROUP BY c.city
    ORDER BY customers DESC
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 4: Customers by Signup Platform",
    """
    SELECT
        COALESCE(signup_platform, 'Unknown') AS signup_platform,
        COUNT(DISTINCT customer_id) AS customers
    FROM customers
    GROUP BY COALESCE(signup_platform, 'Unknown')
    ORDER BY customers DESC
    """,
)

run_query(
    "KPI 5: App Version Mix",
    """
    SELECT
        COALESCE(c.app_version, 'Unknown') AS app_version,
        COUNT(DISTINCT c.customer_id) AS customers
    FROM customers c
    JOIN (
        SELECT DISTINCT customer_id
        FROM orders
        WHERE platform_id = ?
    ) z
        ON c.customer_id = z.customer_id
    GROUP BY COALESCE(c.app_version, 'Unknown')
    ORDER BY customers DESC
    """,
    [zepto_platform_id],
)

run_query(
    "Question 1: Which cities have the largest Zepto customer base?",
    """
    SELECT
        c.city,
        COUNT(DISTINCT c.customer_id) AS customers
    FROM customers c
    JOIN (
        SELECT DISTINCT customer_id
        FROM orders
        WHERE platform_id = ?
    ) z
        ON c.customer_id = z.customer_id
    GROUP BY c.city
    ORDER BY customers DESC
    """,
    [zepto_platform_id],
)

run_query(
    "Question 2: Which cities show the strongest customer acquisition?",
    """
    SELECT
        c.city,
        COUNT(DISTINCT c.customer_id) AS customers_acquired
    FROM customers c
    WHERE LOWER(TRIM(c.signup_platform)) = 'zepto'
    GROUP BY c.city
    ORDER BY customers_acquired DESC
    """,
)

run_query(
    "Question 3: Which signup platform contributes the most customers?",
    """
    SELECT
        COALESCE(signup_platform, 'Unknown') AS signup_platform,
        COUNT(DISTINCT customer_id) AS customers
    FROM customers
    GROUP BY COALESCE(signup_platform, 'Unknown')
    ORDER BY customers DESC
    LIMIT 1
    """,
)

run_query(
    "Question 4: Which cities have high customers but low order activity?",
    """
    WITH customer_city AS (
        SELECT
            c.city,
            COUNT(DISTINCT c.customer_id) AS customers
        FROM customers c
        JOIN (
            SELECT DISTINCT customer_id
            FROM orders
            WHERE platform_id = ?
        ) z
            ON c.customer_id = z.customer_id
        GROUP BY c.city
    ), city_orders AS (
        SELECT
            ds.city,
            COUNT(o.order_id) AS orders
        FROM orders o
        JOIN dark_stores ds
            ON o.store_id = ds.store_id
        WHERE o.platform_id = ?
        GROUP BY ds.city
    )
    SELECT
        cc.city,
        cc.customers,
        COALESCE(co.orders, 0) AS orders,
        ROUND(
            COALESCE(co.orders, 0) * 1.0 / NULLIF(cc.customers, 0),
            2
        ) AS orders_per_customer
    FROM customer_city cc
    LEFT JOIN city_orders co
        ON cc.city = co.city
    ORDER BY orders_per_customer ASC
    LIMIT 15
    """,
    [zepto_platform_id, zepto_platform_id],
)

run_query(
    "Question 5: How does customer growth compare with order growth?",
    """
    WITH yearly_customers AS (
        SELECT
            SUBSTR(c.signup_date, 7, 4) AS year,
            COUNT(DISTINCT c.customer_id) AS new_customers
        FROM customers c
        WHERE LOWER(TRIM(c.signup_platform)) = 'zepto'
          AND c.signup_date IS NOT NULL
        GROUP BY SUBSTR(c.signup_date, 7, 4)
    ), yearly_orders AS (
        SELECT
            SUBSTR(order_datetime, 1, 4) AS year,
            COUNT(*) AS orders
        FROM orders
        WHERE platform_id = ?
        GROUP BY SUBSTR(order_datetime, 1, 4)
    )
    SELECT
        yc.year,
        yc.new_customers,
        COALESCE(yo.orders, 0) AS orders
    FROM yearly_customers yc
    LEFT JOIN yearly_orders yo
        ON yc.year = yo.year

    UNION

    SELECT
        yo.year,
        COALESCE(yc.new_customers, 0) AS new_customers,
        yo.orders
    FROM yearly_orders yo
    LEFT JOIN yearly_customers yc
        ON yo.year = yc.year
    WHERE yc.year IS NULL

    ORDER BY year
    """,
    [zepto_platform_id],
)

# ============================================================
# 6. ZEPTO — ORDERS
# ============================================================

run_query(
    "KPI 1: Total Orders",
    """
    SELECT COUNT(*) AS total_orders
    FROM orders
    WHERE platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 2: Average Order Value",
    """
    SELECT ROUND(AVG(order_value_inr), 2) AS average_order_value
    FROM orders
    WHERE platform_id = ?
      AND order_value_inr IS NOT NULL
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 3: Order Completion Rate",
    """
    SELECT ROUND(
        SUM(CASE WHEN LOWER(order_status) = 'delivered' THEN 1 ELSE 0 END)
        * 100.0 / NULLIF(COUNT(*), 0),
        2
    ) AS order_completion_rate_percent
    FROM orders
    WHERE platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 4: Cancellation Rate",
    """
    SELECT ROUND(
        SUM(CASE WHEN LOWER(order_status) = 'cancelled' THEN 1 ELSE 0 END)
        * 100.0 / NULLIF(COUNT(*), 0),
        2
    ) AS cancellation_rate_percent
    FROM orders
    WHERE platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 5: Return Rate",
    """
    SELECT ROUND(
        SUM(CASE WHEN LOWER(order_status) = 'returned' THEN 1 ELSE 0 END)
        * 100.0 / NULLIF(COUNT(*), 0),
        2
    ) AS return_rate_percent
    FROM orders
    WHERE platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "Question 1: Which cities have the highest order volumes?",
    """
    SELECT
        ds.city,
        COUNT(o.order_id) AS orders
    FROM orders o
    JOIN dark_stores ds
        ON o.store_id = ds.store_id
    WHERE o.platform_id = ?
    GROUP BY ds.city
    ORDER BY orders DESC
    """,
    [zepto_platform_id],
)

run_query(
    "Question 2: Which cities have the highest cancellation rate?",
    """
    SELECT
        ds.city,
        COUNT(o.order_id) AS orders,
        ROUND(
            SUM(CASE WHEN LOWER(o.order_status) = 'cancelled' THEN 1 ELSE 0 END)
            * 100.0 / NULLIF(COUNT(o.order_id), 0),
            2
        ) AS cancellation_rate_percent
    FROM orders o
    JOIN dark_stores ds
        ON o.store_id = ds.store_id
    WHERE o.platform_id = ?
    GROUP BY ds.city
    ORDER BY cancellation_rate_percent DESC
    """,
    [zepto_platform_id],
)

run_query(
    "Question 3: Which stores generate high orders but also high cancellations?",
    """
    SELECT
        o.store_id,
        ds.city,
        COUNT(o.order_id) AS orders,
        SUM(CASE WHEN LOWER(o.order_status) = 'cancelled' THEN 1 ELSE 0 END) AS cancelled_orders,
        ROUND(
            SUM(CASE WHEN LOWER(o.order_status) = 'cancelled' THEN 1 ELSE 0 END)
            * 100.0 / NULLIF(COUNT(o.order_id), 0),
            2
        ) AS cancellation_rate_percent
    FROM orders o
    JOIN dark_stores ds
        ON o.store_id = ds.store_id
    WHERE o.platform_id = ?
    GROUP BY o.store_id, ds.city
    HAVING COUNT(o.order_id) >= 10
    ORDER BY cancellation_rate_percent DESC, orders DESC
    LIMIT 15
    """,
    [zepto_platform_id],
)

run_query(
    "Question 4: How is Zepto's AOV changing over time?",
    """
    SELECT
        SUBSTR(order_datetime, 1, 7) AS month,
        ROUND(AVG(order_value_inr), 2) AS average_order_value,
        COUNT(*) AS orders
    FROM orders
    WHERE platform_id = ?
      AND order_value_inr IS NOT NULL
    GROUP BY SUBSTR(order_datetime, 1, 7)
    ORDER BY month
    """,
    [zepto_platform_id],
)

run_query(
    "Question 5: Where should Zepto focus to improve order completion?",
    """
    SELECT
        ds.city,
        COUNT(o.order_id) AS total_orders,
        SUM(CASE WHEN LOWER(o.order_status) = 'delivered' THEN 1 ELSE 0 END) AS completed_orders,
        SUM(CASE WHEN LOWER(o.order_status) IN ('cancelled', 'returned') THEN 1 ELSE 0 END) AS failed_orders,
        ROUND(
            SUM(CASE WHEN LOWER(o.order_status) = 'delivered' THEN 1 ELSE 0 END)
            * 100.0 / NULLIF(COUNT(o.order_id), 0),
            2
        ) AS completion_rate_percent
    FROM orders o
    JOIN dark_stores ds
        ON o.store_id = ds.store_id
    WHERE o.platform_id = ?
    GROUP BY ds.city
    ORDER BY completion_rate_percent ASC, total_orders DESC
    """,
    [zepto_platform_id],
)

# ============================================================
# 7. ZEPTO — ORDER ITEMS
# ============================================================

run_query(
    "KPI 1: Units Sold",
    """
    SELECT SUM(COALESCE(oi.quantity, 0)) AS units_sold
    FROM order_items oi
    JOIN orders o
        ON oi.order_id = o.order_id
    WHERE o.platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 2: Gross Item Value",
    """
    SELECT ROUND(SUM(COALESCE(oi.line_total_inr, 0)), 2) AS gross_item_value
    FROM order_items oi
    JOIN orders o
        ON oi.order_id = o.order_id
    WHERE o.platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 3: Average Item Price",
    """
    SELECT ROUND(AVG(oi.item_price_inr), 2) AS average_item_price
    FROM order_items oi
    JOIN orders o
        ON oi.order_id = o.order_id
    WHERE o.platform_id = ?
      AND oi.item_price_inr IS NOT NULL
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 4: Average Quantity per Order",
    """
    SELECT ROUND(
        SUM(COALESCE(oi.quantity, 0)) * 1.0
        / NULLIF(COUNT(DISTINCT oi.order_id), 0),
        2
    ) AS average_quantity_per_order
    FROM order_items oi
    JOIN orders o
        ON oi.order_id = o.order_id
    WHERE o.platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 5: Category Contribution",
    """
    WITH category_value AS (
        SELECT
            p.category,
            SUM(COALESCE(oi.line_total_inr, 0)) AS item_revenue
        FROM order_items oi
        JOIN orders o
            ON oi.order_id = o.order_id
        JOIN products p
            ON oi.product_id = p.product_id
        WHERE o.platform_id = ?
        GROUP BY p.category
    ), total_value AS (
        SELECT SUM(item_revenue) AS item_revenue
        FROM category_value
    )
    SELECT ROUND(
        MAX(cv.item_revenue) * 100.0 / NULLIF(tv.item_revenue, 0),
        2
    ) AS top_category_contribution_percent
    FROM category_value cv
    CROSS JOIN total_value tv
    """,
    [zepto_platform_id],
)

run_query(
    "Question 1: Which products are purchased most frequently?",
    """
    SELECT
        p.product_id,
        p.product_name,
        SUM(COALESCE(oi.quantity, 0)) AS units_sold
    FROM order_items oi
    JOIN orders o
        ON oi.order_id = o.order_id
    JOIN products p
        ON oi.product_id = p.product_id
    WHERE o.platform_id = ?
    GROUP BY p.product_id, p.product_name
    ORDER BY units_sold DESC
    LIMIT 15
    """,
    [zepto_platform_id],
)

run_query(
    "Question 2: Which categories generate the most units?",
    """
    SELECT
        p.category,
        SUM(COALESCE(oi.quantity, 0)) AS units_sold
    FROM order_items oi
    JOIN orders o
        ON oi.order_id = o.order_id
    JOIN products p
        ON oi.product_id = p.product_id
    WHERE o.platform_id = ?
    GROUP BY p.category
    ORDER BY units_sold DESC
    """,
    [zepto_platform_id],
)

run_query(
    "Question 3: Which products contribute the most item revenue?",
    """
    SELECT
        p.product_id,
        p.product_name,
        ROUND(SUM(COALESCE(oi.line_total_inr, 0)), 2) AS item_revenue
    FROM order_items oi
    JOIN orders o
        ON oi.order_id = o.order_id
    JOIN products p
        ON oi.product_id = p.product_id
    WHERE o.platform_id = ?
    GROUP BY p.product_id, p.product_name
    ORDER BY item_revenue DESC
    LIMIT 15
    """,
    [zepto_platform_id],
)

run_query(
    "Question 4: Which products have high quantity but low value?",
    """
    SELECT
        p.product_id,
        p.product_name,
        SUM(COALESCE(oi.quantity, 0)) AS units_sold,
        ROUND(SUM(COALESCE(oi.line_total_inr, 0)), 2) AS item_revenue,
        ROUND(
            SUM(COALESCE(oi.line_total_inr, 0))
            / NULLIF(SUM(COALESCE(oi.quantity, 0)), 0),
            2
        ) AS value_per_unit
    FROM order_items oi
    JOIN orders o
        ON oi.order_id = o.order_id
    JOIN products p
        ON oi.product_id = p.product_id
    WHERE o.platform_id = ?
    GROUP BY p.product_id, p.product_name
    HAVING units_sold > 0
    ORDER BY units_sold DESC, value_per_unit ASC
    LIMIT 15
    """,
    [zepto_platform_id],
)

run_query(
    "Question 5: Which products are critical to Zepto's customer basket?",
    """
    WITH product_sales AS (
        SELECT
            p.product_id,
            p.product_name,
            COUNT(DISTINCT oi.order_id) AS orders_containing_product,
            SUM(COALESCE(oi.quantity, 0)) AS units_sold,
            SUM(COALESCE(oi.line_total_inr, 0)) AS revenue
        FROM order_items oi
        JOIN orders o
            ON oi.order_id = o.order_id
        JOIN products p
            ON oi.product_id = p.product_id
        WHERE o.platform_id = ?
        GROUP BY p.product_id, p.product_name
    )
    SELECT
        product_id,
        product_name,
        orders_containing_product,
        units_sold,
        ROUND(revenue, 2) AS revenue
    FROM product_sales
    ORDER BY orders_containing_product DESC, revenue DESC
    LIMIT 15
    """,
    [zepto_platform_id],
)

# ============================================================
# 8. ZEPTO — INVENTORY
# ============================================================

run_query(
    "KPI 1: Total Stock Units",
    """
    SELECT SUM(COALESCE(i.stock_units, 0)) AS total_stock_units
    FROM inventory i
    JOIN dark_stores ds
        ON i.store_id = ds.store_id
    WHERE ds.platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 2: Low-stock SKU Count",
    """
    SELECT COUNT(*) AS low_stock_sku_count
    FROM inventory i
    JOIN dark_stores ds
        ON i.store_id = ds.store_id
    WHERE ds.platform_id = ?
      AND COALESCE(i.stock_units, 0) <= COALESCE(i.reorder_level, 0)
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 3: Stock-to-Reorder Ratio",
    """
    SELECT ROUND(
        SUM(COALESCE(i.stock_units, 0)) * 1.0
        / NULLIF(SUM(COALESCE(i.reorder_level, 0)), 0),
        2
    ) AS stock_to_reorder_ratio
    FROM inventory i
    JOIN dark_stores ds
        ON i.store_id = ds.store_id
    WHERE ds.platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 4: Expiring Inventory",
    """
    SELECT SUM(COALESCE(i.stock_units, 0)) AS expiring_inventory_units
    FROM inventory i
    JOIN dark_stores ds
        ON i.store_id = ds.store_id
    WHERE ds.platform_id = ?
      AND i.expiry_date IS NOT NULL
      AND DATE(i.expiry_date) <= DATE('now', '+30 day')
      AND COALESCE(i.stock_units, 0) > 0
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 5: Inventory Value",
    """
    SELECT ROUND(
        SUM(
            COALESCE(i.stock_units, 0)
            * COALESCE(p.selling_price, 0)
        ),
        2
    ) AS inventory_value
    FROM inventory i
    JOIN dark_stores ds
        ON i.store_id = ds.store_id
    JOIN products p
        ON i.product_id = p.product_id
    WHERE ds.platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "Question 1: Which Zepto stores have the lowest inventory levels?",
    """
    SELECT
        ds.store_id,
        ds.city,
        ROUND(SUM(COALESCE(i.stock_units, 0)), 2) AS stock_units
    FROM inventory i
    JOIN dark_stores ds
        ON i.store_id = ds.store_id
    WHERE ds.platform_id = ?
    GROUP BY ds.store_id, ds.city
    ORDER BY stock_units ASC
    LIMIT 15
    """,
    [zepto_platform_id],
)

run_query(
    "Question 2: Which products are below reorder level?",
    """
    SELECT
        i.product_id,
        p.product_name,
        ds.store_id,
        ds.city,
        ROUND(i.stock_units, 2) AS stock_units,
        ROUND(i.reorder_level, 2) AS reorder_level,
        ROUND(i.reorder_level - i.stock_units, 2) AS stock_shortage
    FROM inventory i
    JOIN dark_stores ds
        ON i.store_id = ds.store_id
    JOIN products p
        ON i.product_id = p.product_id
    WHERE ds.platform_id = ?
      AND COALESCE(i.stock_units, 0) < COALESCE(i.reorder_level, 0)
    ORDER BY stock_shortage DESC
    LIMIT 20
    """,
    [zepto_platform_id],
)

run_query(
    "Question 3: Which stores have excessive stock?",
    """
    SELECT
        ds.store_id,
        ds.city,
        ROUND(SUM(COALESCE(i.stock_units, 0)), 2) AS stock_units,
        ROUND(SUM(COALESCE(i.reorder_level, 0)), 2) AS reorder_level,
        ROUND(
            SUM(COALESCE(i.stock_units, 0)) * 1.0
            / NULLIF(SUM(COALESCE(i.reorder_level, 0)), 0),
            2
        ) AS stock_to_reorder_ratio
    FROM inventory i
    JOIN dark_stores ds
        ON i.store_id = ds.store_id
    WHERE ds.platform_id = ?
    GROUP BY ds.store_id, ds.city
    HAVING stock_to_reorder_ratio > 2
    ORDER BY stock_to_reorder_ratio DESC
    LIMIT 15
    """,
    [zepto_platform_id],
)

run_query(
    "Question 4: Which products are at risk of expiry?",
    """
    SELECT
        i.product_id,
        p.product_name,
        ds.store_id,
        ds.city,
        ROUND(i.stock_units, 2) AS stock_units,
        i.expiry_date
    FROM inventory i
    JOIN dark_stores ds
        ON i.store_id = ds.store_id
    JOIN products p
        ON i.product_id = p.product_id
    WHERE ds.platform_id = ?
      AND i.expiry_date IS NOT NULL
      AND DATE(i.expiry_date) <= DATE('now', '+30 day')
      AND COALESCE(i.stock_units, 0) > 0
    ORDER BY DATE(i.expiry_date) ASC, stock_units DESC
    LIMIT 20
    """,
    [zepto_platform_id],
)

run_query(
    "Question 5: Where is working capital potentially tied up in excess inventory?",
    """
    SELECT
        ds.store_id,
        ds.city,
        ROUND(
            SUM(
                CASE
                    WHEN COALESCE(i.stock_units, 0) > COALESCE(i.reorder_level, 0)
                    THEN (i.stock_units - i.reorder_level)
                         * COALESCE(p.selling_price, 0)
                    ELSE 0
                END
            ),
            2
        ) AS excess_inventory_value
    FROM inventory i
    JOIN dark_stores ds
        ON i.store_id = ds.store_id
    JOIN products p
        ON i.product_id = p.product_id
    WHERE ds.platform_id = ?
    GROUP BY ds.store_id, ds.city
    ORDER BY excess_inventory_value DESC
    LIMIT 15
    """,
    [zepto_platform_id],
)

# ============================================================
# 9. ZEPTO — LOGISTICS
# ============================================================

run_query(
    "KPI 1: Average Delivery Distance",
    """
    SELECT ROUND(AVG(l.distance_km), 2) AS average_delivery_distance_km
    FROM logistics l
    JOIN orders o
        ON l.order_id = o.order_id
    WHERE o.platform_id = ?
      AND l.distance_km IS NOT NULL
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 2: Average Delivery Rating",
    """
    SELECT ROUND(AVG(l.delivery_rating), 2) AS average_delivery_rating
    FROM logistics l
    JOIN orders o
        ON l.order_id = o.order_id
    WHERE o.platform_id = ?
      AND l.delivery_rating IS NOT NULL
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 3: Delay Rate",
    """
    SELECT ROUND(
        SUM(CASE WHEN LOWER(l.delay_flag) IN ('yes', 'y') THEN 1 ELSE 0 END)
        * 100.0 / NULLIF(COUNT(*), 0),
        2
    ) AS delay_rate_percent
    FROM logistics l
    JOIN orders o
        ON l.order_id = o.order_id
    WHERE o.platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 4: On-Time Delivery Rate",
    """
    SELECT ROUND(
        SUM(
            CASE
                WHEN o.actual_delivery_min <= o.promised_delivery_min THEN 1
                ELSE 0
            END
        ) * 100.0 / NULLIF(COUNT(*), 0),
        2
    ) AS on_time_delivery_rate_percent
    FROM logistics l
    JOIN orders o
        ON l.order_id = o.order_id
    WHERE o.platform_id = ?
      AND o.actual_delivery_min IS NOT NULL
      AND o.promised_delivery_min IS NOT NULL
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 5: Delayed Deliveries",
    """
    SELECT COUNT(*) AS delayed_deliveries
    FROM logistics l
    JOIN orders o
        ON l.order_id = o.order_id
    WHERE o.platform_id = ?
      AND LOWER(l.delay_flag) IN ('yes', 'y')
    """,
    [zepto_platform_id],
)

run_query(
    "Question 1: What percentage of Zepto deliveries are delayed?",
    """
    SELECT ROUND(
        SUM(CASE WHEN LOWER(l.delay_flag) IN ('yes', 'y') THEN 1 ELSE 0 END)
        * 100.0 / NULLIF(COUNT(*), 0),
        2
    ) AS delayed_delivery_percent
    FROM logistics l
    JOIN orders o
        ON l.order_id = o.order_id
    WHERE o.platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "Question 2: Which cities experience the highest delay rate?",
    """
    SELECT
        ds.city,
        COUNT(l.delivery_id) AS deliveries,
        ROUND(
            SUM(CASE WHEN LOWER(l.delay_flag) IN ('yes', 'y') THEN 1 ELSE 0 END)
            * 100.0 / NULLIF(COUNT(l.delivery_id), 0),
            2
        ) AS delay_rate_percent
    FROM logistics l
    JOIN orders o
        ON l.order_id = o.order_id
    JOIN dark_stores ds
        ON o.store_id = ds.store_id
    WHERE o.platform_id = ?
    GROUP BY ds.city
    ORDER BY delay_rate_percent DESC
    """,
    [zepto_platform_id],
)

run_query(
    "Question 3: Which vehicle types perform best?",
    """
    SELECT
        l.vehicle_type,
        COUNT(*) AS deliveries,
        ROUND(AVG(l.distance_km), 2) AS average_distance_km,
        ROUND(
            SUM(CASE WHEN LOWER(l.delay_flag) IN ('yes', 'y') THEN 1 ELSE 0 END)
            * 100.0 / NULLIF(COUNT(*), 0),
            2
        ) AS delay_rate_percent,
        ROUND(AVG(l.delivery_rating), 2) AS average_rating
    FROM logistics l
    JOIN orders o
        ON l.order_id = o.order_id
    WHERE o.platform_id = ?
    GROUP BY l.vehicle_type
    ORDER BY delay_rate_percent ASC, average_rating DESC
    """,
    [zepto_platform_id],
)

run_query(
    "Question 4: Does longer delivery distance increase delays?",
    """
    SELECT
        CASE
            WHEN l.distance_km < 3 THEN '0-3 km'
            WHEN l.distance_km < 6 THEN '3-6 km'
            WHEN l.distance_km < 10 THEN '6-10 km'
            ELSE '10+ km'
        END AS distance_band,
        COUNT(*) AS deliveries,
        ROUND(
            SUM(CASE WHEN LOWER(l.delay_flag) IN ('yes', 'y') THEN 1 ELSE 0 END)
            * 100.0 / NULLIF(COUNT(*), 0),
            2
        ) AS delay_rate_percent
    FROM logistics l
    JOIN orders o
        ON l.order_id = o.order_id
    WHERE o.platform_id = ?
      AND l.distance_km IS NOT NULL
    GROUP BY distance_band
    ORDER BY
        CASE distance_band
            WHEN '0-3 km' THEN 1
            WHEN '3-6 km' THEN 2
            WHEN '6-10 km' THEN 3
            ELSE 4
        END
    """,
    [zepto_platform_id],
)

run_query(
    "Question 5: How strongly are delivery delays associated with customer ratings?",
    """
    SELECT
        CASE
            WHEN LOWER(l.delay_flag) IN ('yes', 'y') THEN 'Delayed'
            ELSE 'On Time'
        END AS delivery_status,
        COUNT(*) AS deliveries,
        ROUND(AVG(l.delivery_rating), 2) AS average_rating
    FROM logistics l
    JOIN orders o
        ON l.order_id = o.order_id
    WHERE o.platform_id = ?
      AND l.delivery_rating IS NOT NULL
    GROUP BY delivery_status
    ORDER BY delivery_status
    """,
    [zepto_platform_id],
)

# ============================================================
# 10. ZEPTO — MONTHLY P&L
# ============================================================

run_query(
    "KPI 1: Revenue",
    """
    SELECT ROUND(SUM(revenue_inr), 2) AS revenue
    FROM pnl_monthly_safe
    WHERE platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 2: COGS",
    """
    SELECT ROUND(SUM(cogs_inr), 2) AS cogs
    FROM pnl_monthly_safe
    WHERE platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 3: Operating Cost",
    """
    SELECT ROUND(
        SUM(
            delivery_cost_inr
            + marketing_spend_inr
            + employee_cost_inr
            + other_opex_inr
        ),
        2
    ) AS operating_cost
    FROM pnl_monthly_safe
    WHERE platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 4: Profit",
    """
    SELECT ROUND(SUM(profit_inr), 2) AS profit
    FROM pnl_monthly_safe
    WHERE platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "KPI 5: Profit Margin",
    """
    SELECT ROUND(
        SUM(profit_inr) * 100.0
        / NULLIF(SUM(revenue_inr), 0),
        2
    ) AS profit_margin_percent
    FROM pnl_monthly_safe
    WHERE platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "Question 1: Is Zepto profitable?",
    """
    SELECT
        ROUND(SUM(revenue_inr), 2) AS revenue,
        ROUND(SUM(profit_inr), 2) AS profit,
        ROUND(
            SUM(profit_inr) * 100.0
            / NULLIF(SUM(revenue_inr), 0),
            2
        ) AS profit_margin_percent,
        CASE
            WHEN SUM(profit_inr) > 0 THEN 'Profitable'
            WHEN SUM(profit_inr) < 0 THEN 'Loss Making'
            ELSE 'Break Even'
        END AS profitability_status
    FROM pnl_monthly_safe
    WHERE platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "Question 2: Which cities generate the highest revenue?",
    """
    SELECT
        city,
        ROUND(SUM(revenue_inr), 2) AS revenue
    FROM pnl_monthly_safe
    WHERE platform_id = ?
    GROUP BY city
    ORDER BY revenue DESC
    """,
    [zepto_platform_id],
)

run_query(
    "Question 3: Which cities generate revenue but remain unprofitable?",
    """
    SELECT
        city,
        ROUND(SUM(revenue_inr), 2) AS revenue,
        ROUND(SUM(profit_inr), 2) AS profit,
        ROUND(
            SUM(profit_inr) * 100.0
            / NULLIF(SUM(revenue_inr), 0),
            2
        ) AS profit_margin_percent
    FROM pnl_monthly_safe
    WHERE platform_id = ?
    GROUP BY city
    HAVING SUM(profit_inr) < 0
    ORDER BY revenue DESC
    """,
    [zepto_platform_id],
)

run_query(
    "Question 4: Which cost category hurts Zepto's margins the most?",
    """
    SELECT
        ROUND(SUM(cogs_inr), 2) AS cogs,
        ROUND(SUM(delivery_cost_inr), 2) AS delivery_cost,
        ROUND(SUM(marketing_spend_inr), 2) AS marketing_spend,
        ROUND(SUM(employee_cost_inr), 2) AS employee_cost,
        ROUND(SUM(other_opex_inr), 2) AS other_opex
    FROM pnl_monthly_safe
    WHERE platform_id = ?
    """,
    [zepto_platform_id],
)

run_query(
    "Question 5: How is Zepto's profit changing month by month?",
    """
    SELECT
        month,
        ROUND(SUM(revenue_inr), 2) AS revenue,
        ROUND(SUM(cogs_inr), 2) AS cogs,
        ROUND(
            SUM(
                delivery_cost_inr
                + marketing_spend_inr
                + employee_cost_inr
                + other_opex_inr
            ),
            2
        ) AS operating_cost,
        ROUND(SUM(profit_inr), 2) AS profit,
        ROUND(
            SUM(profit_inr) * 100.0
            / NULLIF(SUM(revenue_inr), 0),
            2
        ) AS profit_margin_percent
    FROM pnl_monthly_safe
    WHERE platform_id = ?
    GROUP BY month
    ORDER BY month
    """,
    [zepto_platform_id],
)


