import os
import sqlite3
import pandas as pd

# ============================================================
# BLINKIT SQL ANALYSIS
# SQLite3 + pandas
# 10 sections | 5 KPIs + 5 business questions each
# ============================================================

# ------------------------------------------------------------
# 1. PROJECT PATHS
# ------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# blinkit.py is expected inside the main project folder.
# The fallback also works if the file is placed inside Analysis.
possible_cleaned_folders = [
    os.path.join(BASE_DIR, "cleaned data"),
    os.path.join(os.path.dirname(BASE_DIR), "cleaned data"),
]

CLEANED_FOLDER = next(
    (folder for folder in possible_cleaned_folders if os.path.isdir(folder)),
    possible_cleaned_folders[0]
)

DATABASE_FOLDER = os.path.join(
    BASE_DIR if os.path.isdir(os.path.join(BASE_DIR, "cleaned data")) else os.path.dirname(BASE_DIR),
    "database"
)
os.makedirs(DATABASE_FOLDER, exist_ok=True)

DATABASE_PATH = os.path.join(DATABASE_FOLDER, "quick_commerce.db")

# ------------------------------------------------------------
# 2. LOAD CLEANED CSV FILES INTO SQLITE
# ------------------------------------------------------------
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

missing_files = []
for file_name in files.values():
    file_path = os.path.join(CLEANED_FOLDER, file_name)
    if not os.path.isfile(file_path):
        missing_files.append(file_path)

if missing_files:
    raise FileNotFoundError(
        "The following cleaned CSV files were not found:\n"
        + "\n".join(missing_files)
    )

conn = sqlite3.connect(DATABASE_PATH)

for table_name, file_name in files.items():
    file_path = os.path.join(CLEANED_FOLDER, file_name)
    df = pd.read_csv(file_path)
    df.to_sql(table_name, conn, if_exists="replace", index=False)

print("SQLite database connected successfully.")
print("Cleaned CSV files loaded into SQLite successfully.")

# ------------------------------------------------------------
# 3. SMALL VALIDATION CHECK
# ------------------------------------------------------------
required_tables = list(files.keys())
existing_tables = pd.read_sql_query(
    """
    SELECT name
    FROM sqlite_master
    WHERE type = 'table'
    """,
    conn,
)["name"].tolist()

missing_tables = [table for table in required_tables if table not in existing_tables]

if missing_tables:
    conn.close()
    raise RuntimeError(
        "These SQLite tables were not created correctly: " + ", ".join(missing_tables)
    )

# ------------------------------------------------------------
# 4. FIND BLINKIT PLATFORM ID
# ------------------------------------------------------------
platform_result = pd.read_sql_query(
    """
    SELECT platform_id
    FROM platforms
    WHERE LOWER(TRIM(platform_name)) = 'blinkit'
    LIMIT 1
    """,
    conn,
)

if platform_result.empty:
    conn.close()
    raise ValueError("Blinkit was not found in the platforms table.")

BLINKIT_PLATFORM_ID = int(platform_result.iloc[0]["platform_id"])

print(f"Blinkit platform_id: {BLINKIT_PLATFORM_ID}")

# ------------------------------------------------------------
# 5. REUSABLE QUERY FUNCTION
# ------------------------------------------------------------
def run_query(question, query, params=None):
    """Run SQL, print the answer, and return the result as a DataFrame."""

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
# 1. BLINKIT — PLATFORM / EXECUTIVE
# ============================================================

# KPI 1: Total Orders
run_query(
    "KPI 1: What is Blinkit's total number of orders?",
    """
    SELECT COUNT(*) AS total_orders
    FROM orders
    WHERE platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 2: Total Revenue
run_query(
    "KPI 2: What is Blinkit's total revenue?",
    """
    SELECT ROUND(COALESCE(SUM(order_value_inr), 0), 2) AS total_revenue
    FROM orders
    WHERE platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 3: Average Order Value
run_query(
    "KPI 3: What is Blinkit's average order value?",
    """
    SELECT ROUND(COALESCE(AVG(order_value_inr), 0), 2) AS average_order_value
    FROM orders
    WHERE platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 4: Discount Rate
run_query(
    "KPI 4: What is Blinkit's discount rate?",
    """
    SELECT
        ROUND(
            COALESCE(SUM(discount_inr), 0) * 100.0 /
            NULLIF(COALESCE(SUM(order_value_inr), 0) + COALESCE(SUM(discount_inr), 0), 0),
            2
        ) AS discount_rate_percent
    FROM orders
    WHERE platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 5: Profit Margin
run_query(
    "KPI 5: What is Blinkit's profit margin?",
    """
    SELECT
        ROUND(
            COALESCE(SUM(revenue_inr), 0)
            - COALESCE(SUM(cogs_inr), 0)
            - COALESCE(SUM(delivery_cost_inr), 0)
            - COALESCE(SUM(marketing_spend_inr), 0)
            - COALESCE(SUM(employee_cost_inr), 0)
            - COALESCE(SUM(other_opex_inr), 0),
            2
        ) * 100.0 /
        NULLIF(COALESCE(SUM(revenue_inr), 0), 0) AS profit_margin_percent
    FROM pnl_monthly
    WHERE platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 1: Is Blinkit gaining or losing business over time?
run_query(
    "Question 1: Is Blinkit gaining or losing business over time?",
    """
    SELECT
        SUBSTR(order_datetime, 1, 7) AS month,
        COUNT(*) AS orders,
        ROUND(COALESCE(SUM(order_value_inr), 0), 2) AS revenue
    FROM orders
    WHERE platform_id = ?
    GROUP BY SUBSTR(order_datetime, 1, 7)
    ORDER BY month
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 2: Which cities are Blinkit's strongest markets?
run_query(
    "Question 2: Which cities are Blinkit's strongest markets?",
    """
    SELECT
        ds.city,
        COUNT(o.order_id) AS orders,
        ROUND(COALESCE(SUM(o.order_value_inr), 0), 2) AS revenue,
        ROUND(COALESCE(AVG(o.order_value_inr), 0), 2) AS aov
    FROM orders o
    JOIN dark_stores ds ON o.store_id = ds.store_id
    WHERE o.platform_id = ?
    GROUP BY ds.city
    ORDER BY revenue DESC, orders DESC
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 3: Is discounting driving Blinkit's order growth?
run_query(
    "Question 3: Is discounting driving Blinkit's order growth?",
    """
    SELECT
        SUBSTR(order_datetime, 1, 7) AS month,
        COUNT(*) AS orders,
        ROUND(COALESCE(SUM(discount_inr), 0), 2) AS discount_value,
        ROUND(
            COALESCE(SUM(discount_inr), 0) * 100.0 /
            NULLIF(COALESCE(SUM(order_value_inr), 0) + COALESCE(SUM(discount_inr), 0), 0),
            2
        ) AS discount_rate_percent
    FROM orders
    WHERE platform_id = ?
    GROUP BY SUBSTR(order_datetime, 1, 7)
    ORDER BY month
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 4: Which operational area is causing the largest performance gap?
run_query(
    "Question 4: Which operational area is causing the largest performance gap?",
    """
    WITH platform_operations AS (
        SELECT
            'Cancellation Rate' AS operational_area,
            ROUND(
                SUM(CASE WHEN order_status = 'Cancelled' THEN 1 ELSE 0 END) * 100.0 /
                NULLIF(COUNT(*), 0),
                2
            ) AS issue_rate
        FROM orders
        WHERE platform_id = ?

        UNION ALL

        SELECT
            'Return Rate' AS operational_area,
            ROUND(
                SUM(CASE WHEN order_status = 'Returned' THEN 1 ELSE 0 END) * 100.0 /
                NULLIF(COUNT(*), 0),
                2
            ) AS issue_rate
        FROM orders
        WHERE platform_id = ?

        UNION ALL

        SELECT
            'Delivery Delay Rate' AS operational_area,
            ROUND(
                SUM(CASE WHEN l.delay_flag = 'Yes' THEN 1 ELSE 0 END) * 100.0 /
                NULLIF(COUNT(*), 0),
                2
            ) AS issue_rate
        FROM logistics l
        JOIN orders o ON l.order_id = o.order_id
        WHERE o.platform_id = ?
    )
    SELECT operational_area, issue_rate
    FROM platform_operations
    ORDER BY issue_rate DESC
    """,
    [BLINKIT_PLATFORM_ID, BLINKIT_PLATFORM_ID, BLINKIT_PLATFORM_ID],
)

# Question 5: What is the single biggest improvement opportunity for Blinkit?
run_query(
    "Question 5: What is the single biggest improvement opportunity for Blinkit?",
    """
    WITH metrics AS (
        SELECT
            'Cancellation Rate' AS opportunity,
            ROUND(
                SUM(CASE WHEN order_status = 'Cancelled' THEN 1 ELSE 0 END) * 100.0 /
                NULLIF(COUNT(*), 0),
                2
            ) AS current_value
        FROM orders
        WHERE platform_id = ?

        UNION ALL

        SELECT
            'Return Rate',
            ROUND(
                SUM(CASE WHEN order_status = 'Returned' THEN 1 ELSE 0 END) * 100.0 /
                NULLIF(COUNT(*), 0),
                2
            )
        FROM orders
        WHERE platform_id = ?

        UNION ALL

        SELECT
            'Delivery Delay Rate',
            ROUND(
                SUM(CASE WHEN l.delay_flag = 'Yes' THEN 1 ELSE 0 END) * 100.0 /
                NULLIF(COUNT(*), 0),
                2
            )
        FROM logistics l
        JOIN orders o ON l.order_id = o.order_id
        WHERE o.platform_id = ?
    )
    SELECT opportunity, current_value
    FROM metrics
    ORDER BY current_value DESC
    LIMIT 1
    """,
    [BLINKIT_PLATFORM_ID, BLINKIT_PLATFORM_ID, BLINKIT_PLATFORM_ID],
)

# ============================================================
# 2. BLINKIT — DARK STORES
# ============================================================

# KPI 1: Store Count
run_query(
    "KPI 1: What is Blinkit's store count?",
    """
    SELECT COUNT(*) AS store_count
    FROM dark_stores
    WHERE platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 2: Orders per Store
run_query(
    "KPI 2: What are Blinkit's orders per store?",
    """
    SELECT ROUND(
        COUNT(o.order_id) * 1.0 / NULLIF(COUNT(DISTINCT ds.store_id), 0),
        2
    ) AS orders_per_store
    FROM dark_stores ds
    LEFT JOIN orders o
        ON ds.store_id = o.store_id
        AND o.platform_id = ?
    WHERE ds.platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID, BLINKIT_PLATFORM_ID],
)

# KPI 3: Average Store Size
run_query(
    "KPI 3: What is Blinkit's average store size?",
    """
    SELECT ROUND(COALESCE(AVG(sqft_area), 0), 2) AS average_store_size_sqft
    FROM dark_stores
    WHERE platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 4: Store Productivity
run_query(
    "KPI 4: What is Blinkit's store productivity?",
    """
    SELECT ROUND(
        COUNT(o.order_id) * 1.0 /
        NULLIF(COALESCE(SUM(ds.sqft_area), 0), 0),
        4
    ) AS orders_per_sqft
    FROM dark_stores ds
    LEFT JOIN orders o
        ON ds.store_id = o.store_id
        AND o.platform_id = ?
    WHERE ds.platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID, BLINKIT_PLATFORM_ID],
)

# KPI 5: Store Contribution
run_query(
    "KPI 5: What is Blinkit's store revenue contribution?",
    """
    WITH store_revenue AS (
        SELECT store_id, COALESCE(SUM(order_value_inr), 0) AS revenue
        FROM orders
        WHERE platform_id = ?
        GROUP BY store_id
    )
    SELECT ROUND(
        MAX(revenue) * 100.0 / NULLIF(SUM(revenue), 0),
        2
    ) AS top_store_revenue_contribution_percent
    FROM store_revenue
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 1: Top performing stores
run_query(
    "Question 1: Which Blinkit dark stores are the top performers?",
    """
    SELECT
        ds.store_id,
        ds.store_name_clean AS store_name,
        ds.city,
        COUNT(o.order_id) AS orders,
        ROUND(COALESCE(SUM(o.order_value_inr), 0), 2) AS revenue
    FROM dark_stores ds
    LEFT JOIN orders o
        ON ds.store_id = o.store_id
        AND o.platform_id = ?
    WHERE ds.platform_id = ?
    GROUP BY ds.store_id, ds.store_name_clean, ds.city
    ORDER BY revenue DESC, orders DESC
    LIMIT 15
    """,
    [BLINKIT_PLATFORM_ID, BLINKIT_PLATFORM_ID],
)

# Question 2: Low utilization stores
run_query(
    "Question 2: Which Blinkit stores have low utilization?",
    """
    WITH store_metrics AS (
        SELECT
            ds.store_id,
            ds.store_name_clean AS store_name,
            ds.city,
            ds.sqft_area,
            COUNT(o.order_id) AS orders,
            COUNT(o.order_id) * 1.0 / NULLIF(ds.sqft_area, 0) AS orders_per_sqft
        FROM dark_stores ds
        LEFT JOIN orders o
            ON ds.store_id = o.store_id
            AND o.platform_id = ?
        WHERE ds.platform_id = ?
        GROUP BY ds.store_id, ds.store_name_clean, ds.city, ds.sqft_area
    ),
    benchmark AS (
        SELECT AVG(orders_per_sqft) AS avg_orders_per_sqft
        FROM store_metrics
    )
    SELECT
        store_id,
        store_name,
        city,
        sqft_area,
        orders,
        ROUND(orders_per_sqft, 4) AS orders_per_sqft
    FROM store_metrics, benchmark
    WHERE orders_per_sqft < avg_orders_per_sqft
    ORDER BY orders_per_sqft ASC
    LIMIT 15
    """,
    [BLINKIT_PLATFORM_ID, BLINKIT_PLATFORM_ID],
)

# Question 3: Cities requiring additional stores
run_query(
    "Question 3: Which cities require additional Blinkit stores?",
    """
    SELECT
        ds.city,
        COUNT(DISTINCT ds.store_id) AS store_count,
        COUNT(o.order_id) AS orders,
        ROUND(
            COUNT(o.order_id) * 1.0 /
            NULLIF(COUNT(DISTINCT ds.store_id), 0),
            2
        ) AS orders_per_store
    FROM dark_stores ds
    LEFT JOIN orders o
        ON ds.store_id = o.store_id
        AND o.platform_id = ?
    WHERE ds.platform_id = ?
    GROUP BY ds.city
    ORDER BY orders_per_store DESC, orders DESC
    """,
    [BLINKIT_PLATFORM_ID, BLINKIT_PLATFORM_ID],
)

# Question 4: Large but underproductive stores
run_query(
    "Question 4: Which Blinkit stores are large but underproductive?",
    """
    WITH store_metrics AS (
        SELECT
            ds.store_id,
            ds.store_name_clean AS store_name,
            ds.city,
            ds.sqft_area,
            COUNT(o.order_id) AS orders,
            COUNT(o.order_id) * 1.0 / NULLIF(ds.sqft_area, 0) AS orders_per_sqft
        FROM dark_stores ds
        LEFT JOIN orders o
            ON ds.store_id = o.store_id
            AND o.platform_id = ?
        WHERE ds.platform_id = ?
        GROUP BY ds.store_id, ds.store_name_clean, ds.city, ds.sqft_area
    ),
    benchmarks AS (
        SELECT
            AVG(sqft_area) AS avg_sqft,
            AVG(orders_per_sqft) AS avg_productivity
        FROM store_metrics
    )
    SELECT
        store_id,
        store_name,
        city,
        sqft_area,
        orders,
        ROUND(orders_per_sqft, 4) AS orders_per_sqft
    FROM store_metrics, benchmarks
    WHERE sqft_area > avg_sqft
      AND orders_per_sqft < avg_productivity
    ORDER BY sqft_area DESC
    LIMIT 15
    """,
    [BLINKIT_PLATFORM_ID, BLINKIT_PLATFORM_ID],
)

# Question 5: Biggest operational opportunity
run_query(
    "Question 5: Which Blinkit store is the biggest operational opportunity?",
    """
    WITH store_metrics AS (
        SELECT
            ds.store_id,
            ds.store_name_clean AS store_name,
            ds.city,
            ds.sqft_area,
            COUNT(o.order_id) AS orders,
            COUNT(o.order_id) * 1.0 / NULLIF(ds.sqft_area, 0) AS orders_per_sqft
        FROM dark_stores ds
        LEFT JOIN orders o
            ON ds.store_id = o.store_id
            AND o.platform_id = ?
        WHERE ds.platform_id = ?
        GROUP BY ds.store_id, ds.store_name_clean, ds.city, ds.sqft_area
    ),
    ranked AS (
        SELECT *,
               ROW_NUMBER() OVER (
                   ORDER BY orders_per_sqft ASC, sqft_area DESC
               ) AS rank_position
        FROM store_metrics
        WHERE orders_per_sqft IS NOT NULL
    )
    SELECT
        store_id,
        store_name,
        city,
        sqft_area,
        orders,
        ROUND(orders_per_sqft, 4) AS orders_per_sqft
    FROM ranked
    WHERE rank_position = 1
    """,
    [BLINKIT_PLATFORM_ID, BLINKIT_PLATFORM_ID],
)

# ============================================================
# 3. BLINKIT — EMPLOYEES
# ============================================================

# KPI 1: Employee Count
run_query(
    "KPI 1: What is Blinkit's total employee count?",
    """
    SELECT COUNT(*) AS employee_count
    FROM employees e
    JOIN dark_stores ds ON e.store_id = ds.store_id
    WHERE ds.platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 2: Active Workforce
run_query(
    "KPI 2: What is Blinkit's active workforce?",
    """
    SELECT COUNT(*) AS active_workforce
    FROM employees e
    JOIN dark_stores ds ON e.store_id = ds.store_id
    WHERE ds.platform_id = ?
      AND LOWER(TRIM(e.employment_status)) = 'active'
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 3: Average Salary
run_query(
    "KPI 3: What is Blinkit's average monthly salary?",
    """
    SELECT ROUND(COALESCE(AVG(e.monthly_salary_inr), 0), 2) AS average_monthly_salary
    FROM employees e
    JOIN dark_stores ds ON e.store_id = ds.store_id
    WHERE ds.platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 4: Employees per Store
run_query(
    "KPI 4: What are Blinkit's employees per store?",
    """
    SELECT ROUND(
        COUNT(e.employee_id) * 1.0 /
        NULLIF(COUNT(DISTINCT ds.store_id), 0),
        2
    ) AS employees_per_store
    FROM dark_stores ds
    LEFT JOIN employees e ON ds.store_id = e.store_id
    WHERE ds.platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 5: Employee Cost per Order
run_query(
    "KPI 5: What is Blinkit's employee cost per order?",
    """
    SELECT ROUND(
        COALESCE(SUM(employee_cost_inr), 0) /
        NULLIF(COALESCE(SUM(orders_count), 0), 0),
        2
    ) AS employee_cost_per_order
    FROM pnl_monthly
    WHERE platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 1: Understaffed stores
run_query(
    "Question 1: Which Blinkit stores are understaffed?",
    """
    WITH store_load AS (
        SELECT
            ds.store_id,
            ds.store_name_clean AS store_name,
            ds.city,
            COUNT(DISTINCT e.employee_id) AS employees,
            COUNT(DISTINCT o.order_id) AS orders,
            COUNT(DISTINCT o.order_id) * 1.0 /
            NULLIF(COUNT(DISTINCT e.employee_id), 0) AS orders_per_employee
        FROM dark_stores ds
        LEFT JOIN employees e ON ds.store_id = e.store_id
        LEFT JOIN orders o
            ON ds.store_id = o.store_id
            AND o.platform_id = ?
        WHERE ds.platform_id = ?
        GROUP BY ds.store_id, ds.store_name_clean, ds.city
    )
    SELECT
        store_id,
        store_name,
        city,
        employees,
        orders,
        ROUND(orders_per_employee, 2) AS orders_per_employee
    FROM store_load
    WHERE employees > 0
    ORDER BY orders_per_employee DESC
    LIMIT 15
    """,
    [BLINKIT_PLATFORM_ID, BLINKIT_PLATFORM_ID],
)

# Question 2: Overstaffed stores
run_query(
    "Question 2: Which Blinkit stores are overstaffed relative to orders?",
    """
    WITH store_load AS (
        SELECT
            ds.store_id,
            ds.store_name_clean AS store_name,
            ds.city,
            COUNT(DISTINCT e.employee_id) AS employees,
            COUNT(DISTINCT o.order_id) AS orders,
            COUNT(DISTINCT e.employee_id) * 1.0 /
            NULLIF(COUNT(DISTINCT o.order_id), 0) AS employees_per_order
        FROM dark_stores ds
        LEFT JOIN employees e ON ds.store_id = e.store_id
        LEFT JOIN orders o
            ON ds.store_id = o.store_id
            AND o.platform_id = ?
        WHERE ds.platform_id = ?
        GROUP BY ds.store_id, ds.store_name_clean, ds.city
    )
    SELECT
        store_id,
        store_name,
        city,
        employees,
        orders,
        ROUND(employees_per_order, 4) AS employees_per_order
    FROM store_load
    WHERE orders > 0
    ORDER BY employees_per_order DESC
    LIMIT 15
    """,
    [BLINKIT_PLATFORM_ID, BLINKIT_PLATFORM_ID],
)

# Question 3: Roles with highest employee cost
run_query(
    "Question 3: Which roles consume the most employee cost?",
    """
    SELECT
        e.role,
        COUNT(*) AS employee_count,
        ROUND(COALESCE(SUM(e.monthly_salary_inr), 0), 2) AS employee_cost,
        ROUND(COALESCE(AVG(e.monthly_salary_inr), 0), 2) AS average_salary
    FROM employees e
    JOIN dark_stores ds ON e.store_id = ds.store_id
    WHERE ds.platform_id = ?
    GROUP BY e.role
    ORDER BY employee_cost DESC
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 4: City with highest workforce expense
run_query(
    "Question 4: Which city has the highest workforce expense?",
    """
    SELECT
        ds.city,
        COUNT(e.employee_id) AS employee_count,
        ROUND(COALESCE(SUM(e.monthly_salary_inr), 0), 2) AS workforce_expense
    FROM employees e
    JOIN dark_stores ds ON e.store_id = ds.store_id
    WHERE ds.platform_id = ?
    GROUP BY ds.city
    ORDER BY workforce_expense DESC
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 5: Employee productivity by city
run_query(
    "Question 5: How does employee productivity vary by city?",
    """
    SELECT
        ds.city,
        COUNT(DISTINCT e.employee_id) AS employees,
        COUNT(DISTINCT o.order_id) AS orders,
        ROUND(
            COUNT(DISTINCT o.order_id) * 1.0 /
            NULLIF(COUNT(DISTINCT e.employee_id), 0),
            2
        ) AS orders_per_employee
    FROM dark_stores ds
    LEFT JOIN employees e ON ds.store_id = e.store_id
    LEFT JOIN orders o
        ON ds.store_id = o.store_id
        AND o.platform_id = ?
    WHERE ds.platform_id = ?
    GROUP BY ds.city
    ORDER BY orders_per_employee DESC
    """,
    [BLINKIT_PLATFORM_ID, BLINKIT_PLATFORM_ID],
)

# ============================================================
# 4. BLINKIT — PRODUCTS
# ============================================================

# KPI 1: Product Count
run_query(
    "KPI 1: What is Blinkit's product count?",
    """
    SELECT COUNT(DISTINCT oi.product_id) AS product_count
    FROM order_items oi
    JOIN orders o ON oi.order_id = o.order_id
    WHERE o.platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 2: Average Selling Price
run_query(
    "KPI 2: What is Blinkit's average selling price?",
    """
    SELECT ROUND(COALESCE(AVG(p.selling_price), 0), 2) AS average_selling_price
    FROM products p
    WHERE p.product_id IN (
        SELECT DISTINCT oi.product_id
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
    )
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 3: Average Discount
run_query(
    "KPI 3: What is Blinkit's average product discount?",
    """
    SELECT ROUND(COALESCE(AVG(p.discount_percent), 0), 2) AS average_discount_percent
    FROM products p
    WHERE p.product_id IN (
        SELECT DISTINCT oi.product_id
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
    )
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 4: Category Count
run_query(
    "KPI 4: How many product categories does Blinkit have?",
    """
    SELECT COUNT(DISTINCT p.category) AS category_count
    FROM products p
    WHERE p.product_id IN (
        SELECT DISTINCT oi.product_id
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
    )
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 5: Outlier Products
run_query(
    "KPI 5: How many Blinkit products are price outliers?",
    """
    SELECT COUNT(*) AS outlier_products
    FROM products p
    WHERE LOWER(TRIM(p.price_status)) = 'outlier'
      AND p.product_id IN (
          SELECT DISTINCT oi.product_id
          FROM order_items oi
          JOIN orders o ON oi.order_id = o.order_id
          WHERE o.platform_id = ?
      )
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 1: Important categories
run_query(
    "Question 1: Which product categories are most important to Blinkit?",
    """
    SELECT
        p.category,
        COUNT(DISTINCT oi.product_id) AS products_sold,
        SUM(COALESCE(oi.quantity, 0)) AS units_sold,
        ROUND(COALESCE(SUM(oi.line_total_inr), 0), 2) AS item_revenue
    FROM order_items oi
    JOIN products p ON oi.product_id = p.product_id
    JOIN orders o ON oi.order_id = o.order_id
    WHERE o.platform_id = ?
    GROUP BY p.category
    ORDER BY item_revenue DESC, units_sold DESC
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 2: Highest discounts by category
run_query(
    "Question 2: Which product categories receive the highest discounts?",
    """
    SELECT
        category,
        ROUND(COALESCE(AVG(discount_percent), 0), 2) AS average_discount_percent,
        COUNT(*) AS product_count
    FROM products
    GROUP BY category
    ORDER BY average_discount_percent DESC
    """,
)

# Question 3: Brands dominate assortment
run_query(
    "Question 3: Which brands dominate Blinkit's assortment?",
    """
    SELECT
        COALESCE(brand, 'Unknown') AS brand,
        COUNT(*) AS product_count,
        ROUND(COALESCE(AVG(selling_price), 0), 2) AS average_selling_price
    FROM products
    GROUP BY COALESCE(brand, 'Unknown')
    ORDER BY product_count DESC, average_selling_price DESC
    LIMIT 15
    """,
)

# Question 4: Products to promote
run_query(
    "Question 4: Which products should Blinkit promote?",
    """
    SELECT
        p.product_id,
        p.product_name,
        p.category,
        SUM(COALESCE(oi.quantity, 0)) AS units_sold,
        ROUND(COALESCE(SUM(oi.line_total_inr), 0), 2) AS item_revenue
    FROM order_items oi
    JOIN products p ON oi.product_id = p.product_id
    JOIN orders o ON oi.order_id = o.order_id
    WHERE o.platform_id = ?
    GROUP BY p.product_id, p.product_name, p.category
    ORDER BY units_sold DESC, item_revenue DESC
    LIMIT 15
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 5: Products needing pricing review
run_query(
    "Question 5: Which products need pricing review?",
    """
    SELECT
        p.product_id,
        p.product_name,
        p.category,
        ROUND(p.mrp, 2) AS mrp,
        ROUND(p.selling_price, 2) AS selling_price,
        ROUND(p.discount_percent, 2) AS discount_percent,
        p.price_status,
        COALESCE(SUM(oi.quantity), 0) AS units_sold
    FROM products p
    LEFT JOIN order_items oi ON p.product_id = oi.product_id
    LEFT JOIN orders o
        ON oi.order_id = o.order_id
        AND o.platform_id = ?
    WHERE p.price_status = 'Outlier'
       OR p.discount_percent > (
            SELECT AVG(discount_percent)
            FROM products
       )
    GROUP BY
        p.product_id, p.product_name, p.category,
        p.mrp, p.selling_price, p.discount_percent, p.price_status
    ORDER BY p.price_status = 'Outlier' DESC, p.discount_percent DESC
    LIMIT 15
    """,
    [BLINKIT_PLATFORM_ID],
)

# ============================================================
# 5. BLINKIT — CUSTOMERS
# ============================================================

# KPI 1: Customer Count
run_query(
    "KPI 1: What is Blinkit's customer count?",
    """
    SELECT COUNT(DISTINCT c.customer_id) AS customer_count
    FROM customers c
    WHERE LOWER(TRIM(c.signup_platform)) = 'blinkit'
    """,
)

# KPI 2: Customer Growth
run_query(
    "KPI 2: What is Blinkit's customer growth?",
    """
    SELECT
        SUBSTR(signup_date, 1, 7) AS signup_month,
        COUNT(DISTINCT customer_id) AS new_customers
    FROM customers
    WHERE LOWER(TRIM(signup_platform)) = 'blinkit'
    GROUP BY SUBSTR(signup_date, 1, 7)
    ORDER BY signup_month
    """,
)

# KPI 3: Customers by City
run_query(
    "KPI 3: What is Blinkit's customer distribution by city?",
    """
    SELECT
        city,
        COUNT(DISTINCT customer_id) AS customer_count
    FROM customers
    WHERE LOWER(TRIM(signup_platform)) = 'blinkit'
    GROUP BY city
    ORDER BY customer_count DESC
    """,
)

# KPI 4: Customers by Signup Platform
run_query(
    "KPI 4: How are Blinkit customers distributed by signup platform?",
    """
    SELECT
        signup_platform,
        COUNT(DISTINCT customer_id) AS customer_count
    FROM customers
    GROUP BY signup_platform
    ORDER BY customer_count DESC
    """,
)

# KPI 5: App Version Mix
run_query(
    "KPI 5: What is Blinkit's app version mix?",
    """
    SELECT
        app_version,
        COUNT(DISTINCT customer_id) AS customer_count
    FROM customers
    WHERE LOWER(TRIM(signup_platform)) = 'blinkit'
    GROUP BY app_version
    ORDER BY customer_count DESC
    """,
)

# Question 1: Strongest customer cities
run_query(
    "Question 1: Which cities have the strongest Blinkit customer base?",
    """
    SELECT
        city,
        COUNT(DISTINCT customer_id) AS customers
    FROM customers
    WHERE LOWER(TRIM(signup_platform)) = 'blinkit'
    GROUP BY city
    ORDER BY customers DESC
    """,
)

# Question 2: Weak customer acquisition
run_query(
    "Question 2: Where is Blinkit's customer acquisition weak?",
    """
    SELECT
        city,
        COUNT(DISTINCT customer_id) AS new_customers
    FROM customers
    WHERE LOWER(TRIM(signup_platform)) = 'blinkit'
    GROUP BY city
    ORDER BY new_customers ASC
    """,
)

# Question 3: Best signup platforms
run_query(
    "Question 3: Which signup platforms perform best?",
    """
    SELECT
        signup_platform,
        COUNT(DISTINCT customer_id) AS customers
    FROM customers
    GROUP BY signup_platform
    ORDER BY customers DESC
    """,
)

# Question 4: Large customer base but weak orders
run_query(
    "Question 4: Which cities have large customer bases but weak orders?",
    """
    WITH customer_city AS (
        SELECT
            city,
            COUNT(DISTINCT customer_id) AS customers
        FROM customers
        WHERE LOWER(TRIM(signup_platform)) = 'blinkit'
        GROUP BY city
    ),
    order_city AS (
        SELECT
            ds.city,
            COUNT(o.order_id) AS orders
        FROM orders o
        JOIN dark_stores ds ON o.store_id = ds.store_id
        WHERE o.platform_id = ?
        GROUP BY ds.city
    )
    SELECT
        c.city,
        c.customers,
        COALESCE(o.orders, 0) AS orders,
        ROUND(
            COALESCE(o.orders, 0) * 1.0 / NULLIF(c.customers, 0),
            2
        ) AS orders_per_customer
    FROM customer_city c
    LEFT JOIN order_city o ON c.city = o.city
    ORDER BY orders_per_customer ASC, c.customers DESC
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 5: Customer growth -> order growth
run_query(
    "Question 5: Is Blinkit's customer growth converting into order growth?",
    """
    WITH monthly_customers AS (
        SELECT
            SUBSTR(signup_date, 1, 7) AS month,
            COUNT(DISTINCT customer_id) AS new_customers
        FROM customers
        WHERE LOWER(TRIM(signup_platform)) = 'blinkit'
        GROUP BY SUBSTR(signup_date, 1, 7)
    ),
    monthly_orders AS (
        SELECT
            SUBSTR(order_datetime, 1, 7) AS month,
            COUNT(*) AS orders
        FROM orders
        WHERE platform_id = ?
        GROUP BY SUBSTR(order_datetime, 1, 7)
    )
    SELECT
        c.month,
        c.new_customers,
        COALESCE(o.orders, 0) AS orders
    FROM monthly_customers c
    LEFT JOIN monthly_orders o ON c.month = o.month

    UNION ALL

    SELECT
        o.month,
        0 AS new_customers,
        o.orders
    FROM monthly_orders o
    WHERE o.month NOT IN (SELECT month FROM monthly_customers)
    ORDER BY month
    """,
    [BLINKIT_PLATFORM_ID],
)

# ============================================================
# 6. BLINKIT — ORDERS
# ============================================================

# KPI 1: Orders
run_query(
    "KPI 1: What is Blinkit's total order count?",
    """
    SELECT COUNT(*) AS orders
    FROM orders
    WHERE platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 2: AOV
run_query(
    "KPI 2: What is Blinkit's average order value?",
    """
    SELECT ROUND(COALESCE(AVG(order_value_inr), 0), 2) AS aov
    FROM orders
    WHERE platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 3: Delivered Rate
run_query(
    "KPI 3: What is Blinkit's delivered rate?",
    """
    SELECT ROUND(
        SUM(CASE WHEN order_status = 'Delivered' THEN 1 ELSE 0 END) * 100.0 /
        NULLIF(COUNT(*), 0),
        2
    ) AS delivered_rate_percent
    FROM orders
    WHERE platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 4: Cancellation Rate
run_query(
    "KPI 4: What is Blinkit's cancellation rate?",
    """
    SELECT ROUND(
        SUM(CASE WHEN order_status = 'Cancelled' THEN 1 ELSE 0 END) * 100.0 /
        NULLIF(COUNT(*), 0),
        2
    ) AS cancellation_rate_percent
    FROM orders
    WHERE platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 5: Return Rate
run_query(
    "KPI 5: What is Blinkit's return rate?",
    """
    SELECT ROUND(
        SUM(CASE WHEN order_status = 'Returned' THEN 1 ELSE 0 END) * 100.0 /
        NULLIF(COUNT(*), 0),
        2
    ) AS return_rate_percent
    FROM orders
    WHERE platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 1: Highest order volume cities
run_query(
    "Question 1: Where does Blinkit have the highest order volume?",
    """
    SELECT
        ds.city,
        COUNT(o.order_id) AS orders,
        ROUND(COALESCE(SUM(o.order_value_inr), 0), 2) AS revenue
    FROM orders o
    JOIN dark_stores ds ON o.store_id = ds.store_id
    WHERE o.platform_id = ?
    GROUP BY ds.city
    ORDER BY orders DESC
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 2: Highest cancellation stores
run_query(
    "Question 2: Which stores have the highest cancellation rate?",
    """
    SELECT
        ds.store_id,
        ds.store_name_clean AS store_name,
        ds.city,
        COUNT(o.order_id) AS total_orders,
        ROUND(
            SUM(CASE WHEN o.order_status = 'Cancelled' THEN 1 ELSE 0 END) * 100.0 /
            NULLIF(COUNT(o.order_id), 0),
            2
        ) AS cancellation_rate_percent
    FROM dark_stores ds
    JOIN orders o ON ds.store_id = o.store_id
    WHERE ds.platform_id = ?
      AND o.platform_id = ?
    GROUP BY ds.store_id, ds.store_name_clean, ds.city
    HAVING COUNT(o.order_id) > 0
    ORDER BY cancellation_rate_percent DESC
    LIMIT 15
    """,
    [BLINKIT_PLATFORM_ID, BLINKIT_PLATFORM_ID],
)

# Question 3: Cities with most returns
run_query(
    "Question 3: Which cities have the most returned orders?",
    """
    SELECT
        ds.city,
        COUNT(*) AS returned_orders
    FROM orders o
    JOIN dark_stores ds ON o.store_id = ds.store_id
    WHERE o.platform_id = ?
      AND o.order_status = 'Returned'
    GROUP BY ds.city
    ORDER BY returned_orders DESC
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 4: AOV changing over time
run_query(
    "Question 4: How is Blinkit's AOV changing over time?",
    """
    SELECT
        SUBSTR(order_datetime, 1, 7) AS month,
        COUNT(*) AS orders,
        ROUND(COALESCE(AVG(order_value_inr), 0), 2) AS aov
    FROM orders
    WHERE platform_id = ?
    GROUP BY SUBSTR(order_datetime, 1, 7)
    ORDER BY month
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 5: Operational intervention cities
run_query(
    "Question 5: Which cities need operational intervention?",
    """
    SELECT
        ds.city,
        COUNT(*) AS orders,
        ROUND(
            SUM(CASE WHEN o.order_status = 'Cancelled' THEN 1 ELSE 0 END) * 100.0 /
            NULLIF(COUNT(*), 0),
            2
        ) AS cancellation_rate,
        ROUND(
            SUM(CASE WHEN o.order_status = 'Returned' THEN 1 ELSE 0 END) * 100.0 /
            NULLIF(COUNT(*), 0),
            2
        ) AS return_rate
    FROM orders o
    JOIN dark_stores ds ON o.store_id = ds.store_id
    WHERE o.platform_id = ?
    GROUP BY ds.city
    ORDER BY cancellation_rate DESC, return_rate DESC
    """,
    [BLINKIT_PLATFORM_ID],
)

# ============================================================
# 7. BLINKIT — ORDER ITEMS
# ============================================================

# KPI 1: Units Sold
run_query(
    "KPI 1: What are Blinkit's total units sold?",
    """
    SELECT SUM(COALESCE(oi.quantity, 0)) AS units_sold
    FROM order_items oi
    JOIN orders o ON oi.order_id = o.order_id
    WHERE o.platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 2: Gross Item Revenue
run_query(
    "KPI 2: What is Blinkit's gross item revenue?",
    """
    SELECT ROUND(COALESCE(SUM(oi.line_total_inr), 0), 2) AS gross_item_revenue
    FROM order_items oi
    JOIN orders o ON oi.order_id = o.order_id
    WHERE o.platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 3: Average Item Price
run_query(
    "KPI 3: What is Blinkit's average item price?",
    """
    SELECT ROUND(COALESCE(AVG(oi.item_price_inr), 0), 2) AS average_item_price
    FROM order_items oi
    JOIN orders o ON oi.order_id = o.order_id
    WHERE o.platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 4: Average Quantity per Order
run_query(
    "KPI 4: What is Blinkit's average quantity per order?",
    """
    SELECT ROUND(
        COALESCE(SUM(oi.quantity), 0) * 1.0 /
        NULLIF(COUNT(DISTINCT oi.order_id), 0),
        2
    ) AS average_quantity_per_order
    FROM order_items oi
    JOIN orders o ON oi.order_id = o.order_id
    WHERE o.platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 5: Category Contribution
run_query(
    "KPI 5: What is Blinkit's category contribution?",
    """
    WITH category_sales AS (
        SELECT
            p.category,
            COALESCE(SUM(oi.line_total_inr), 0) AS category_revenue
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.order_id
        JOIN products p ON oi.product_id = p.product_id
        WHERE o.platform_id = ?
        GROUP BY p.category
    )
    SELECT
        category,
        ROUND(category_revenue, 2) AS category_revenue,
        ROUND(
            category_revenue * 100.0 /
            NULLIF((SELECT SUM(category_revenue) FROM category_sales), 0),
            2
        ) AS contribution_percent
    FROM category_sales
    ORDER BY category_revenue DESC
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 1: Frequently purchased products
run_query(
    "Question 1: What products are most frequently purchased?",
    """
    SELECT
        p.product_id,
        p.product_name,
        p.category,
        SUM(COALESCE(oi.quantity, 0)) AS units_sold
    FROM order_items oi
    JOIN orders o ON oi.order_id = o.order_id
    JOIN products p ON oi.product_id = p.product_id
    WHERE o.platform_id = ?
    GROUP BY p.product_id, p.product_name, p.category
    ORDER BY units_sold DESC
    LIMIT 15
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 2: Category units
run_query(
    "Question 2: Which categories generate the most units?",
    """
    SELECT
        p.category,
        SUM(COALESCE(oi.quantity, 0)) AS units_sold
    FROM order_items oi
    JOIN orders o ON oi.order_id = o.order_id
    JOIN products p ON oi.product_id = p.product_id
    WHERE o.platform_id = ?
    GROUP BY p.category
    ORDER BY units_sold DESC
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 3: Product value drivers
run_query(
    "Question 3: Which products generate the most item revenue?",
    """
    SELECT
        p.product_id,
        p.product_name,
        p.category,
        ROUND(COALESCE(SUM(oi.line_total_inr), 0), 2) AS item_revenue
    FROM order_items oi
    JOIN orders o ON oi.order_id = o.order_id
    JOIN products p ON oi.product_id = p.product_id
    WHERE o.platform_id = ?
    GROUP BY p.product_id, p.product_name, p.category
    ORDER BY item_revenue DESC
    LIMIT 15
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 4: Typical basket
run_query(
    "Question 4: What does the typical Blinkit customer basket look like?",
    """
    SELECT
        ROUND(
            COALESCE(SUM(oi.quantity), 0) * 1.0 /
            NULLIF(COUNT(DISTINCT oi.order_id), 0),
            2
        ) AS average_units_per_order,
        ROUND(
            COUNT(DISTINCT oi.product_id) * 1.0 /
            NULLIF(COUNT(DISTINCT oi.order_id), 0),
            2
        ) AS average_unique_products_per_order,
        ROUND(COALESCE(AVG(o.order_value_inr), 0), 2) AS average_order_value
    FROM order_items oi
    JOIN orders o ON oi.order_id = o.order_id
    WHERE o.platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 5: Strategically critical products
run_query(
    "Question 5: Which products are strategically critical to Blinkit's assortment?",
    """
    SELECT
        p.product_id,
        p.product_name,
        p.category,
        SUM(COALESCE(oi.quantity, 0)) AS units_sold,
        ROUND(COALESCE(SUM(oi.line_total_inr), 0), 2) AS item_revenue
    FROM order_items oi
    JOIN orders o ON oi.order_id = o.order_id
    JOIN products p ON oi.product_id = p.product_id
    WHERE o.platform_id = ?
    GROUP BY p.product_id, p.product_name, p.category
    ORDER BY item_revenue DESC, units_sold DESC
    LIMIT 15
    """,
    [BLINKIT_PLATFORM_ID],
)

# ============================================================
# 8. BLINKIT — INVENTORY
# ============================================================

# KPI 1: Stock Units
run_query(
    "KPI 1: What are Blinkit's total stock units?",
    """
    SELECT SUM(COALESCE(i.stock_units, 0)) AS stock_units
    FROM inventory i
    JOIN dark_stores ds ON i.store_id = ds.store_id
    WHERE ds.platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 2: Low-stock Products
run_query(
    "KPI 2: How many Blinkit inventory records are low-stock?",
    """
    SELECT COUNT(*) AS low_stock_products
    FROM inventory i
    JOIN dark_stores ds ON i.store_id = ds.store_id
    WHERE ds.platform_id = ?
      AND COALESCE(i.stock_units, 0) <= COALESCE(i.reorder_level, 0)
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 3: Reorder Risk
run_query(
    "KPI 3: What is Blinkit's reorder risk?",
    """
    SELECT ROUND(
        SUM(
            CASE
                WHEN COALESCE(i.stock_units, 0) <= COALESCE(i.reorder_level, 0)
                THEN 1 ELSE 0
            END
        ) * 100.0 /
        NULLIF(COUNT(*), 0),
        2
    ) AS reorder_risk_percent
    FROM inventory i
    JOIN dark_stores ds ON i.store_id = ds.store_id
    WHERE ds.platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 4: Expiry Risk
run_query(
    "KPI 4: What is Blinkit's expiry risk?",
    """
    SELECT COUNT(*) AS expiry_risk_records
    FROM inventory i
    JOIN dark_stores ds ON i.store_id = ds.store_id
    WHERE ds.platform_id = ?
      AND i.expiry_date IS NOT NULL
      AND julianday(i.expiry_date) - julianday(i.last_restock_date) <= 30
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 5: Inventory per Store
run_query(
    "KPI 5: What is Blinkit's inventory per store?",
    """
    SELECT ROUND(
        COALESCE(SUM(i.stock_units), 0) * 1.0 /
        NULLIF(COUNT(DISTINCT ds.store_id), 0),
        2
    ) AS inventory_per_store
    FROM inventory i
    JOIN dark_stores ds ON i.store_id = ds.store_id
    WHERE ds.platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 1: Stores facing shortages
run_query(
    "Question 1: Which Blinkit stores face stock shortages?",
    """
    SELECT
        ds.store_id,
        ds.store_name_clean AS store_name,
        ds.city,
        COUNT(*) AS low_stock_skus,
        SUM(COALESCE(i.stock_units, 0)) AS stock_units
    FROM inventory i
    JOIN dark_stores ds ON i.store_id = ds.store_id
    WHERE ds.platform_id = ?
      AND COALESCE(i.stock_units, 0) <= COALESCE(i.reorder_level, 0)
    GROUP BY ds.store_id, ds.store_name_clean, ds.city
    ORDER BY low_stock_skus DESC, stock_units ASC
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 2: Products below reorder levels
run_query(
    "Question 2: Which products are below reorder levels?",
    """
    SELECT
        i.product_id,
        p.product_name,
        p.category,
        COUNT(*) AS affected_stores,
        SUM(COALESCE(i.stock_units, 0)) AS total_stock,
        ROUND(COALESCE(AVG(i.reorder_level), 0), 2) AS average_reorder_level
    FROM inventory i
    JOIN dark_stores ds ON i.store_id = ds.store_id
    JOIN products p ON i.product_id = p.product_id
    WHERE ds.platform_id = ?
      AND COALESCE(i.stock_units, 0) <= COALESCE(i.reorder_level, 0)
    GROUP BY i.product_id, p.product_name, p.category
    ORDER BY affected_stores DESC, total_stock ASC
    LIMIT 15
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 3: Overstocked products
run_query(
    "Question 3: Which products are overstocked?",
    """
    SELECT
        i.product_id,
        p.product_name,
        p.category,
        SUM(COALESCE(i.stock_units, 0)) AS total_stock,
        ROUND(COALESCE(AVG(i.reorder_level), 0), 2) AS average_reorder_level,
        ROUND(
            SUM(COALESCE(i.stock_units, 0)) * 1.0 /
            NULLIF(AVG(i.reorder_level), 0),
            2
        ) AS stock_to_reorder_ratio
    FROM inventory i
    JOIN dark_stores ds ON i.store_id = ds.store_id
    JOIN products p ON i.product_id = p.product_id
    WHERE ds.platform_id = ?
    GROUP BY i.product_id, p.product_name, p.category
    HAVING stock_to_reorder_ratio >= 3
    ORDER BY stock_to_reorder_ratio DESC
    LIMIT 15
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 4: Products close to expiry
run_query(
    "Question 4: Which products are close to expiry?",
    """
    SELECT
        i.product_id,
        p.product_name,
        p.category,
        ds.city,
        i.stock_units,
        i.last_restock_date,
        i.expiry_date,
        CAST(
            julianday(i.expiry_date) - julianday(i.last_restock_date)
            AS INTEGER
        ) AS shelf_life_days
    FROM inventory i
    JOIN dark_stores ds ON i.store_id = ds.store_id
    JOIN products p ON i.product_id = p.product_id
    WHERE ds.platform_id = ?
      AND i.expiry_date IS NOT NULL
    ORDER BY shelf_life_days ASC, i.stock_units DESC
    LIMIT 15
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 5: Reduce stockouts without excess stock
run_query(
    "Question 5: How can Blinkit reduce stockouts without increasing excess stock?",
    """
    WITH stock_metrics AS (
        SELECT
            p.product_id,
            p.product_name,
            p.category,
            SUM(COALESCE(i.stock_units, 0)) AS stock_units,
            SUM(COALESCE(i.reorder_level, 0)) AS reorder_units,
            SUM(
                CASE
                    WHEN COALESCE(i.stock_units, 0) <= COALESCE(i.reorder_level, 0)
                    THEN 1 ELSE 0
                END
            ) AS low_stock_locations
        FROM inventory i
        JOIN dark_stores ds ON i.store_id = ds.store_id
        JOIN products p ON i.product_id = p.product_id
        WHERE ds.platform_id = ?
        GROUP BY p.product_id, p.product_name, p.category
    )
    SELECT
        product_id,
        product_name,
        category,
        stock_units,
        reorder_units,
        low_stock_locations,
        ROUND(
            stock_units * 1.0 / NULLIF(reorder_units, 0),
            2
        ) AS stock_to_reorder_ratio
    FROM stock_metrics
    WHERE low_stock_locations > 0
    ORDER BY low_stock_locations DESC, stock_to_reorder_ratio ASC
    LIMIT 15
    """,
    [BLINKIT_PLATFORM_ID],
)

# ============================================================
# 9. BLINKIT — LOGISTICS
# ============================================================

# KPI 1: Delay Rate
run_query(
    "KPI 1: What is Blinkit's delay rate?",
    """
    SELECT ROUND(
        SUM(CASE WHEN l.delay_flag = 'Yes' THEN 1 ELSE 0 END) * 100.0 /
        NULLIF(COUNT(*), 0),
        2
    ) AS delay_rate_percent
    FROM logistics l
    JOIN orders o ON l.order_id = o.order_id
    WHERE o.platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 2: Average Distance
run_query(
    "KPI 2: What is Blinkit's average delivery distance?",
    """
    SELECT ROUND(COALESCE(AVG(l.distance_km), 0), 2) AS average_distance_km
    FROM logistics l
    JOIN orders o ON l.order_id = o.order_id
    WHERE o.platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 3: Delivery Rating
run_query(
    "KPI 3: What is Blinkit's average delivery rating?",
    """
    SELECT ROUND(COALESCE(AVG(l.delivery_rating), 0), 2) AS average_delivery_rating
    FROM logistics l
    JOIN orders o ON l.order_id = o.order_id
    WHERE o.platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 4: Average Distance by Vehicle
run_query(
    "KPI 4: What is the average distance by vehicle type for Blinkit?",
    """
    SELECT
        l.vehicle_type,
        ROUND(COALESCE(AVG(l.distance_km), 0), 2) AS average_distance_km
    FROM logistics l
    JOIN orders o ON l.order_id = o.order_id
    WHERE o.platform_id = ?
    GROUP BY l.vehicle_type
    ORDER BY average_distance_km DESC
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 5: Delayed Deliveries
run_query(
    "KPI 5: How many Blinkit deliveries were delayed?",
    """
    SELECT COUNT(*) AS delayed_deliveries
    FROM logistics l
    JOIN orders o ON l.order_id = o.order_id
    WHERE o.platform_id = ?
      AND l.delay_flag = 'Yes'
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 1: Cities with highest delays
run_query(
    "Question 1: Which cities have the highest delivery delays?",
    """
    SELECT
        ds.city,
        COUNT(*) AS deliveries,
        ROUND(
            SUM(CASE WHEN l.delay_flag = 'Yes' THEN 1 ELSE 0 END) * 100.0 /
            NULLIF(COUNT(*), 0),
            2
        ) AS delay_rate_percent
    FROM logistics l
    JOIN orders o ON l.order_id = o.order_id
    JOIN dark_stores ds ON o.store_id = ds.store_id
    WHERE o.platform_id = ?
    GROUP BY ds.city
    ORDER BY delay_rate_percent DESC
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 2: Distance explains delays
run_query(
    "Question 2: Does delivery distance explain delays?",
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
            SUM(CASE WHEN l.delay_flag = 'Yes' THEN 1 ELSE 0 END) * 100.0 /
            NULLIF(COUNT(*), 0),
            2
        ) AS delay_rate_percent
    FROM logistics l
    JOIN orders o ON l.order_id = o.order_id
    WHERE o.platform_id = ?
    GROUP BY distance_band
    ORDER BY MIN(l.distance_km)
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 3: Most efficient vehicle
run_query(
    "Question 3: Which vehicle type is most efficient?",
    """
    SELECT
        l.vehicle_type,
        COUNT(*) AS deliveries,
        ROUND(COALESCE(AVG(l.distance_km), 0), 2) AS average_distance_km,
        ROUND(
            SUM(CASE WHEN l.delay_flag = 'Yes' THEN 1 ELSE 0 END) * 100.0 /
            NULLIF(COUNT(*), 0),
            2
        ) AS delay_rate_percent,
        ROUND(COALESCE(AVG(l.delivery_rating), 0), 2) AS average_rating
    FROM logistics l
    JOIN orders o ON l.order_id = o.order_id
    WHERE o.platform_id = ?
    GROUP BY l.vehicle_type
    ORDER BY delay_rate_percent ASC, average_rating DESC
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 4: Poor delivery ratings by city
run_query(
    "Question 4: Which cities receive poor delivery ratings?",
    """
    SELECT
        ds.city,
        COUNT(*) AS deliveries,
        ROUND(COALESCE(AVG(l.delivery_rating), 0), 2) AS average_rating,
        ROUND(
            SUM(CASE WHEN l.delay_flag = 'Yes' THEN 1 ELSE 0 END) * 100.0 /
            NULLIF(COUNT(*), 0),
            2
        ) AS delay_rate_percent
    FROM logistics l
    JOIN orders o ON l.order_id = o.order_id
    JOIN dark_stores ds ON o.store_id = ds.store_id
    WHERE o.platform_id = ?
    GROUP BY ds.city
    ORDER BY average_rating ASC
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 5: Improve delivery reliability
run_query(
    "Question 5: How can Blinkit improve delivery reliability?",
    """
    SELECT
        ds.city,
        l.vehicle_type,
        COUNT(*) AS deliveries,
        ROUND(
            SUM(CASE WHEN l.delay_flag = 'Yes' THEN 1 ELSE 0 END) * 100.0 /
            NULLIF(COUNT(*), 0),
            2
        ) AS delay_rate_percent,
        ROUND(COALESCE(AVG(l.distance_km), 0), 2) AS average_distance_km,
        ROUND(COALESCE(AVG(l.delivery_rating), 0), 2) AS average_rating
    FROM logistics l
    JOIN orders o ON l.order_id = o.order_id
    JOIN dark_stores ds ON o.store_id = ds.store_id
    WHERE o.platform_id = ?
    GROUP BY ds.city, l.vehicle_type
    ORDER BY delay_rate_percent DESC, average_rating ASC
    LIMIT 20
    """,
    [BLINKIT_PLATFORM_ID],
)

# ============================================================
# 10. BLINKIT — MONTHLY P&L
# ============================================================

# KPI 1: Revenue
run_query(
    "KPI 1: What is Blinkit's P&L revenue?",
    """
    SELECT ROUND(COALESCE(SUM(revenue_inr), 0), 2) AS revenue
    FROM pnl_monthly
    WHERE platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 2: COGS
run_query(
    "KPI 2: What is Blinkit's P&L COGS?",
    """
    SELECT ROUND(COALESCE(SUM(cogs_inr), 0), 2) AS cogs
    FROM pnl_monthly
    WHERE platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 3: Total Operating Cost
run_query(
    "KPI 3: What is Blinkit's total operating cost?",
    """
    SELECT ROUND(
        COALESCE(SUM(delivery_cost_inr), 0)
        + COALESCE(SUM(marketing_spend_inr), 0)
        + COALESCE(SUM(employee_cost_inr), 0)
        + COALESCE(SUM(other_opex_inr), 0),
        2
    ) AS total_operating_cost
    FROM pnl_monthly
    WHERE platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 4: Profit
run_query(
    "KPI 4: What is Blinkit's profit?",
    """
    SELECT ROUND(
        COALESCE(SUM(revenue_inr), 0)
        - COALESCE(SUM(cogs_inr), 0)
        - COALESCE(SUM(delivery_cost_inr), 0)
        - COALESCE(SUM(marketing_spend_inr), 0)
        - COALESCE(SUM(employee_cost_inr), 0)
        - COALESCE(SUM(other_opex_inr), 0),
        2
    ) AS profit
    FROM pnl_monthly
    WHERE platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# KPI 5: Margin %
run_query(
    "KPI 5: What is Blinkit's profit margin percentage?",
    """
    SELECT ROUND(
        (
            COALESCE(SUM(revenue_inr), 0)
            - COALESCE(SUM(cogs_inr), 0)
            - COALESCE(SUM(delivery_cost_inr), 0)
            - COALESCE(SUM(marketing_spend_inr), 0)
            - COALESCE(SUM(employee_cost_inr), 0)
            - COALESCE(SUM(other_opex_inr), 0)
        ) * 100.0 /
        NULLIF(COALESCE(SUM(revenue_inr), 0), 0),
        2
    ) AS margin_percent
    FROM pnl_monthly
    WHERE platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 1: Revenue by city
run_query(
    "Question 1: Which cities generate the most revenue?",
    """
    SELECT
        city,
        ROUND(COALESCE(SUM(revenue_inr), 0), 2) AS revenue
    FROM pnl_monthly
    WHERE platform_id = ?
    GROUP BY city
    ORDER BY revenue DESC
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 2: Most profitable cities
run_query(
    "Question 2: Which cities are most profitable?",
    """
    SELECT
        city,
        ROUND(
            COALESCE(SUM(revenue_inr), 0)
            - COALESCE(SUM(cogs_inr), 0)
            - COALESCE(SUM(delivery_cost_inr), 0)
            - COALESCE(SUM(marketing_spend_inr), 0)
            - COALESCE(SUM(employee_cost_inr), 0)
            - COALESCE(SUM(other_opex_inr), 0),
            2
        ) AS profit
    FROM pnl_monthly
    WHERE platform_id = ?
    GROUP BY city
    ORDER BY profit DESC
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 3: Costs hurting margin
run_query(
    "Question 3: Which costs hurt Blinkit's margin the most?",
    """
    SELECT
        ROUND(COALESCE(SUM(cogs_inr), 0), 2) AS cogs,
        ROUND(COALESCE(SUM(delivery_cost_inr), 0), 2) AS delivery_cost,
        ROUND(COALESCE(SUM(marketing_spend_inr), 0), 2) AS marketing_spend,
        ROUND(COALESCE(SUM(employee_cost_inr), 0), 2) AS employee_cost,
        ROUND(COALESCE(SUM(other_opex_inr), 0), 2) AS other_opex
    FROM pnl_monthly
    WHERE platform_id = ?
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 4: Marketing efficiency
run_query(
    "Question 4: Is marketing spend efficient?",
    """
    SELECT
        month,
        ROUND(COALESCE(revenue_inr, 0), 2) AS revenue,
        ROUND(COALESCE(marketing_spend_inr, 0), 2) AS marketing_spend,
        ROUND(
            COALESCE(revenue_inr, 0) /
            NULLIF(COALESCE(marketing_spend_inr, 0), 0),
            2
        ) AS revenue_per_marketing_rupee
    FROM pnl_monthly
    WHERE platform_id = ?
    ORDER BY month
    """,
    [BLINKIT_PLATFORM_ID],
)

# Question 5: Profit trend
run_query(
    "Question 5: How does Blinkit's profit trend over time?",
    """
    SELECT
        month,
        ROUND(
            COALESCE(revenue_inr, 0)
            - COALESCE(cogs_inr, 0)
            - COALESCE(delivery_cost_inr, 0)
            - COALESCE(marketing_spend_inr, 0)
            - COALESCE(employee_cost_inr, 0)
            - COALESCE(other_opex_inr, 0),
            2
        ) AS profit,
        ROUND(
            (
                COALESCE(revenue_inr, 0)
                - COALESCE(cogs_inr, 0)
                - COALESCE(delivery_cost_inr, 0)
                - COALESCE(marketing_spend_inr, 0)
                - COALESCE(employee_cost_inr, 0)
                - COALESCE(other_opex_inr, 0)
            ) * 100.0 /
            NULLIF(COALESCE(revenue_inr, 0), 0),
            2
        ) AS margin_percent
    FROM pnl_monthly
    WHERE platform_id = ?
    ORDER BY month
    """,
    [BLINKIT_PLATFORM_ID],
)


