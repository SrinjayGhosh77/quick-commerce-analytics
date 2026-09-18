import sqlite3
from pathlib import Path
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent

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
        "Could not find the 'cleaned data' folder. Keep this file inside SDLC Main."
    )

CLEANED_FOLDER = PROJECT_DIR / "cleaned data"
DATABASE_FOLDER = PROJECT_DIR / "database"
DATABASE_FOLDER.mkdir(exist_ok=True)
DATABASE_PATH = DATABASE_FOLDER / "quick_commerce.db"

conn = sqlite3.connect(DATABASE_PATH)
print("SQLite database connected successfully.")
print(f"Project folder: {PROJECT_DIR}")

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

    for column in [
        "platform_id", "store_id", "employee_id", "product_id",
        "customer_id", "order_id", "order_item_id",
        "inventory_id", "delivery_id", "pnl_id"
    ]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    for column in [
        "sqft_area", "monthly_salary_inr", "mrp", "selling_price",
        "discount_percent", "quantity", "item_price_inr",
        "line_total_inr", "stock_units", "reorder_level",
        "distance_km", "delivery_rating", "promised_delivery_min",
        "actual_delivery_min", "order_value_inr", "discount_inr",
        "revenue_inr", "cogs_inr", "delivery_cost_inr",
        "marketing_spend_inr", "employee_cost_inr", "other_opex_inr",
        "orders_count"
    ]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    if "city" in df.columns:
        df["city"] = df["city"].astype("string").str.strip().str.title()

    if table_name == "dark_stores":
        if "city_clean" not in df.columns and "city" in df.columns:
            df["city_clean"] = df["city"]
        if "store_name_clean" not in df.columns and "store_name" in df.columns:
            df["store_name_clean"] = df["store_name"]

    if table_name == "employees":
        if "employment_status" in df.columns:
            status = df["employment_status"].astype("string").str.strip().str.lower()
            df["work_status"] = status.map({
                "active": "Currently Working",
                "working": "Currently Working",
                "on leave": "On Leave",
                "resigned": "Not Working",
                "terminated": "Not Working",
            }).fillna("Unknown")
        elif "work_status" not in df.columns:
            df["work_status"] = "Unknown"

    df.to_sql(table_name, conn, if_exists="replace", index=False)

instamart_result = pd.read_sql_query(
    """
    SELECT platform_id
    FROM platforms
    WHERE LOWER(TRIM(platform_name)) = 'swiggy instamart'
    LIMIT 1
    """,
    conn,
)

if instamart_result.empty:
    conn.close()
    raise ValueError("Swiggy Instamart was not found in the platforms table.")

instamart_platform_id = int(instamart_result.iloc[0]["platform_id"])
print(f"Swiggy Instamart platform_id: {instamart_platform_id}")

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

def run_query(question, query, params=None):
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
# 1. INSTAMART — PLATFORM / EXECUTIVE
# ============================================================

run_query(
    "KPI 1: Revenue",
    """
    SELECT ROUND(SUM(order_value_inr), 2) AS revenue
    FROM orders
    WHERE platform_id = ?
      AND order_value_inr IS NOT NULL
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 2: Orders",
    """
    SELECT COUNT(*) AS orders
    FROM orders
    WHERE platform_id = ?
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 3: Average Order Value (AOV)",
    """
    SELECT ROUND(AVG(order_value_inr), 2) AS aov
    FROM orders
    WHERE platform_id = ?
      AND order_value_inr IS NOT NULL
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 4: Profit Margin",
    """
    SELECT ROUND(
        SUM(profit_inr) * 100.0 / NULLIF(SUM(revenue_inr), 0),
        2
    ) AS profit_margin_percent
    FROM pnl_monthly_safe
    WHERE platform_id = ?
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 5: Discount Rate",
    """
    SELECT ROUND(
        SUM(COALESCE(discount_inr, 0)) * 100.0
        / NULLIF(SUM(COALESCE(order_value_inr, 0)), 0),
        2
    ) AS discount_rate_percent
    FROM orders
    WHERE platform_id = ?
    """,
    [instamart_platform_id],
)

run_query(
    "Question 1: Which cities drive Instamart's growth?",
    """
    WITH city_year AS (
        SELECT
            city,
            SUBSTR(month, 1, 4) AS year,
            SUM(revenue_inr) AS revenue
        FROM pnl_monthly_safe
        WHERE platform_id = ?
        GROUP BY city, SUBSTR(month, 1, 4)
    ),
    city_bounds AS (
        SELECT
            city,
            MIN(year) AS first_year,
            MAX(year) AS last_year
        FROM city_year
        GROUP BY city
    )
    SELECT
        cy.city,
        cb.first_year,
        cb.last_year,
        ROUND(MAX(
            CASE WHEN cy.year = cb.first_year THEN cy.revenue END
        ), 2) AS first_year_revenue,
        ROUND(MAX(
            CASE WHEN cy.year = cb.last_year THEN cy.revenue END
        ), 2) AS last_year_revenue,
        ROUND(
            (
                MAX(CASE WHEN cy.year = cb.last_year THEN cy.revenue END)
                - MAX(CASE WHEN cy.year = cb.first_year THEN cy.revenue END)
            ) * 100.0
            / NULLIF(
                MAX(CASE WHEN cy.year = cb.first_year THEN cy.revenue END),
                0
            ),
            2
        ) AS growth_percent
    FROM city_year cy
    JOIN city_bounds cb
        ON cy.city = cb.city
    GROUP BY cy.city, cb.first_year, cb.last_year
    ORDER BY growth_percent DESC
    """,
    [instamart_platform_id],
)

run_query(
    "Question 2: Which cities are profitable?",
    """
    SELECT
        city,
        ROUND(SUM(revenue_inr), 2) AS revenue,
        ROUND(SUM(profit_inr), 2) AS profit,
        ROUND(
            SUM(profit_inr) * 100.0 / NULLIF(SUM(revenue_inr), 0),
            2
        ) AS profit_margin_percent
    FROM pnl_monthly_safe
    WHERE platform_id = ?
    GROUP BY city
    ORDER BY profit DESC
    """,
    [instamart_platform_id],
)

run_query(
    "Question 3: Which cities have weak unit economics?",
    """
    WITH city_orders AS (
        SELECT
            ds.city,
            COUNT(o.order_id) AS orders,
            AVG(o.order_value_inr) AS aov
        FROM orders o
        JOIN dark_stores ds
            ON o.store_id = ds.store_id
        WHERE o.platform_id = ?
        GROUP BY ds.city
    ),
    city_profit AS (
        SELECT
            city,
            SUM(revenue_inr) AS revenue,
            SUM(profit_inr) AS profit
        FROM pnl_monthly_safe
        WHERE platform_id = ?
        GROUP BY city
    )
    SELECT
        co.city,
        co.orders,
        ROUND(co.aov, 2) AS aov,
        ROUND(cp.revenue, 2) AS revenue,
        ROUND(cp.profit, 2) AS profit,
        ROUND(
            cp.profit * 1.0 / NULLIF(co.orders, 0),
            2
        ) AS profit_per_order,
        ROUND(
            cp.profit * 100.0 / NULLIF(cp.revenue, 0),
            2
        ) AS profit_margin_percent
    FROM city_orders co
    LEFT JOIN city_profit cp
        ON co.city = cp.city
    ORDER BY profit_per_order ASC
    """,
    [instamart_platform_id, instamart_platform_id],
)

run_query(
    "Question 4: How important are discounts to order generation?",
    """
    SELECT
        SUBSTR(order_datetime, 1, 7) AS month,
        COUNT(*) AS orders,
        ROUND(SUM(COALESCE(discount_inr, 0)), 2) AS total_discount,
        ROUND(SUM(COALESCE(order_value_inr, 0)), 2) AS total_order_value,
        ROUND(
            SUM(COALESCE(discount_inr, 0)) * 100.0
            / NULLIF(SUM(COALESCE(order_value_inr, 0)), 0),
            2
        ) AS discount_rate_percent
    FROM orders
    WHERE platform_id = ?
    GROUP BY SUBSTR(order_datetime, 1, 7)
    ORDER BY month
    """,
    [instamart_platform_id],
)

run_query(
    "Question 5: What is Instamart's largest business opportunity?",
    """
    WITH city_performance AS (
        SELECT
            city,
            SUM(revenue_inr) AS revenue,
            SUM(profit_inr) AS profit
        FROM pnl_monthly_safe
        WHERE platform_id = ?
        GROUP BY city
    )
    SELECT
        city,
        ROUND(revenue, 2) AS revenue,
        ROUND(profit, 2) AS profit,
        ROUND(
            profit * 100.0 / NULLIF(revenue, 0),
            2
        ) AS profit_margin_percent,
        CASE
            WHEN profit < 0 THEN 'High Priority: Loss Making'
            WHEN profit * 100.0 / NULLIF(revenue, 0) < 10
                THEN 'High Priority: Low Margin'
            ELSE 'Stable'
        END AS opportunity_status
    FROM city_performance
    ORDER BY
        CASE WHEN profit < 0 THEN 0 ELSE 1 END,
        profit_margin_percent ASC,
        revenue DESC
    LIMIT 10
    """,
    [instamart_platform_id],
)


# ============================================================
# 2. INSTAMART — DARK STORES
# ============================================================

run_query(
    "KPI 1: Store Count",
    """
    SELECT COUNT(*) AS store_count
    FROM dark_stores
    WHERE platform_id = ?
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 2: Orders per Store",
    """
    SELECT ROUND(
        (SELECT COUNT(*) FROM orders WHERE platform_id = ?) * 1.0
        / NULLIF(
            (SELECT COUNT(*) FROM dark_stores WHERE platform_id = ?),
            0
        ),
        2
    ) AS orders_per_store
    """,
    [instamart_platform_id, instamart_platform_id],
)

run_query(
    "KPI 3: Average Store Size",
    """
    SELECT ROUND(AVG(sqft_area), 2) AS average_store_size_sqft
    FROM dark_stores
    WHERE platform_id = ?
      AND sqft_area IS NOT NULL
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 4: Store Productivity",
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
    [instamart_platform_id, instamart_platform_id],
)

run_query(
    "KPI 5: Store Contribution",
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
    )
    SELECT ROUND(
        MAX(revenue) * 100.0 / NULLIF(SUM(revenue), 0),
        2
    ) AS top_store_revenue_contribution_percent
    FROM store_revenue
    """,
    [instamart_platform_id, instamart_platform_id],
)

run_query(
    "Question 1: Which Instamart stores lead in orders?",
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
    [instamart_platform_id, instamart_platform_id],
)

run_query(
    "Question 2: Which stores underperform?",
    """
    SELECT
        ds.store_id,
        COALESCE(ds.store_name_clean, ds.store_name) AS store_name,
        ds.city,
        ROUND(ds.sqft_area, 2) AS sqft_area,
        COUNT(o.order_id) AS orders,
        ROUND(
            COUNT(o.order_id) * 1.0
            / NULLIF(ds.sqft_area, 0),
            4
        ) AS orders_per_sqft
    FROM dark_stores ds
    LEFT JOIN orders o
        ON ds.store_id = o.store_id
       AND o.platform_id = ?
    WHERE ds.platform_id = ?
    GROUP BY ds.store_id, store_name, ds.city, ds.sqft_area
    ORDER BY orders_per_sqft ASC, orders ASC
    LIMIT 15
    """,
    [instamart_platform_id, instamart_platform_id],
)

run_query(
    "Question 3: Which cities require more stores?",
    """
    SELECT
        ds.city,
        COUNT(DISTINCT ds.store_id) AS store_count,
        COUNT(o.order_id) AS orders,
        ROUND(
            COUNT(o.order_id) * 1.0
            / NULLIF(COUNT(DISTINCT ds.store_id), 0),
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
    [instamart_platform_id, instamart_platform_id],
)

run_query(
    "Question 4: Which stores are underutilized?",
    """
    SELECT
        ds.store_id,
        COALESCE(ds.store_name_clean, ds.store_name) AS store_name,
        ds.city,
        ROUND(ds.sqft_area, 2) AS sqft_area,
        COUNT(o.order_id) AS orders,
        ROUND(
            COUNT(o.order_id) * 1.0
            / NULLIF(ds.sqft_area, 0),
            4
        ) AS orders_per_sqft
    FROM dark_stores ds
    LEFT JOIN orders o
        ON ds.store_id = o.store_id
       AND o.platform_id = ?
    WHERE ds.platform_id = ?
      AND ds.sqft_area IS NOT NULL
    GROUP BY ds.store_id, store_name, ds.city, ds.sqft_area
    ORDER BY orders_per_sqft ASC
    LIMIT 15
    """,
    [instamart_platform_id, instamart_platform_id],
)

run_query(
    "Question 5: Which dark store is the largest source of inefficiency?",
    """
    SELECT
        ds.store_id,
        COALESCE(ds.store_name_clean, ds.store_name) AS store_name,
        ds.city,
        ROUND(ds.sqft_area, 2) AS sqft_area,
        COUNT(o.order_id) AS orders,
        ROUND(
            COUNT(o.order_id) * 1.0
            / NULLIF(ds.sqft_area, 0),
            4
        ) AS orders_per_sqft,
        CASE
            WHEN COUNT(o.order_id) = 0 THEN 'Immediate Attention'
            WHEN COUNT(o.order_id) * 1.0
                 / NULLIF(ds.sqft_area, 0) < 0.50
                THEN 'High Inefficiency'
            WHEN COUNT(o.order_id) * 1.0
                 / NULLIF(ds.sqft_area, 0) < 1.00
                THEN 'Needs Optimization'
            ELSE 'Normal'
        END AS efficiency_status
    FROM dark_stores ds
    LEFT JOIN orders o
        ON ds.store_id = o.store_id
       AND o.platform_id = ?
    WHERE ds.platform_id = ?
    GROUP BY ds.store_id, store_name, ds.city, ds.sqft_area
    ORDER BY orders_per_sqft ASC, sqft_area DESC
    LIMIT 15
    """,
    [instamart_platform_id, instamart_platform_id],
)


# ============================================================
# 3. INSTAMART — EMPLOYEES
# ============================================================

run_query(
    "KPI 1: Total Workforce",
    """
    SELECT COUNT(*) AS total_workforce
    FROM employees e
    JOIN dark_stores ds
        ON e.store_id = ds.store_id
    WHERE ds.platform_id = ?
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 2: Active Employees",
    """
    SELECT COUNT(*) AS active_employees
    FROM employees e
    JOIN dark_stores ds
        ON e.store_id = ds.store_id
    WHERE ds.platform_id = ?
      AND e.work_status = 'Currently Working'
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 3: Average Salary",
    """
    SELECT ROUND(AVG(e.monthly_salary_inr), 2) AS average_salary
    FROM employees e
    JOIN dark_stores ds
        ON e.store_id = ds.store_id
    WHERE ds.platform_id = ?
      AND e.monthly_salary_inr IS NOT NULL
    """,
    [instamart_platform_id],
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
    [instamart_platform_id],
)

run_query(
    "KPI 5: Employee Cost per Order",
    """
    SELECT ROUND(
        (
            SELECT SUM(COALESCE(e.monthly_salary_inr, 0))
            FROM employees e
            JOIN dark_stores ds
                ON e.store_id = ds.store_id
            WHERE ds.platform_id = ?
              AND e.work_status = 'Currently Working'
        )
        / NULLIF(
            (
                SELECT COUNT(*)
                FROM orders
                WHERE platform_id = ?
            ),
            0
        ),
        2
    ) AS employee_cost_per_order
    """,
    [instamart_platform_id, instamart_platform_id],
)

run_query(
    "Question 1: Which stores have the highest staffing levels?",
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
    [instamart_platform_id],
)

run_query(
    "Question 2: Which stores are understaffed?",
    """
    WITH store_orders AS (
        SELECT store_id, COUNT(*) AS orders
        FROM orders
        WHERE platform_id = ?
        GROUP BY store_id
    ),
    store_employees AS (
        SELECT
            e.store_id,
            COUNT(*) AS active_employees
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
        COALESCE(se.active_employees, 0) AS active_employees,
        ROUND(
            COALESCE(so.orders, 0) * 1.0
            / NULLIF(COALESCE(se.active_employees, 0), 0),
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
    [instamart_platform_id, instamart_platform_id, instamart_platform_id],
)

run_query(
    "Question 3: Which roles cost the most?",
    """
    SELECT
        e.role,
        COUNT(*) AS employees,
        ROUND(
            SUM(COALESCE(e.monthly_salary_inr, 0)),
            2
        ) AS salary_cost
    FROM employees e
    JOIN dark_stores ds
        ON e.store_id = ds.store_id
    WHERE ds.platform_id = ?
    GROUP BY e.role
    ORDER BY salary_cost DESC
    """,
    [instamart_platform_id],
)

run_query(
    "Question 4: Which cities have the highest employee cost?",
    """
    SELECT
        ds.city,
        COUNT(e.employee_id) AS employees,
        ROUND(
            SUM(COALESCE(e.monthly_salary_inr, 0)),
            2
        ) AS workforce_cost
    FROM employees e
    JOIN dark_stores ds
        ON e.store_id = ds.store_id
    WHERE ds.platform_id = ?
    GROUP BY ds.city
    ORDER BY workforce_cost DESC
    """,
    [instamart_platform_id],
)

run_query(
    "Question 5: Is staffing proportional to orders?",
    """
    WITH city_employees AS (
        SELECT
            ds.city,
            COUNT(e.employee_id) AS active_employees
        FROM employees e
        JOIN dark_stores ds
            ON e.store_id = ds.store_id
        WHERE ds.platform_id = ?
          AND e.work_status = 'Currently Working'
        GROUP BY ds.city
    ),
    city_orders AS (
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
        ce.active_employees,
        COALESCE(co.orders, 0) AS orders,
        ROUND(
            COALESCE(co.orders, 0) * 1.0
            / NULLIF(ce.active_employees, 0),
            2
        ) AS orders_per_employee,
        CASE
            WHEN COALESCE(co.orders, 0) * 1.0
                 / NULLIF(ce.active_employees, 0) > 1000
                THEN 'High Workload'
            WHEN COALESCE(co.orders, 0) * 1.0
                 / NULLIF(ce.active_employees, 0) < 500
                THEN 'Low Workload'
            ELSE 'Balanced'
        END AS staffing_status
    FROM city_employees ce
    LEFT JOIN city_orders co
        ON ce.city = co.city
    ORDER BY orders_per_employee DESC
    """,
    [instamart_platform_id, instamart_platform_id],
)


# ============================================================
# 4. INSTAMART — PRODUCTS
# ============================================================

run_query(
    "KPI 1: Product Count",
    """
    SELECT COUNT(DISTINCT oi.product_id) AS product_count
    FROM order_items oi
    JOIN orders o
        ON oi.order_id = o.order_id
    WHERE o.platform_id = ?
    """,
    [instamart_platform_id],
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
    ) x
        ON p.product_id = x.product_id
    WHERE p.selling_price IS NOT NULL
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 3: Discount %",
    """
    SELECT ROUND(AVG(p.discount_percent), 2) AS average_discount_percent
    FROM products p
    JOIN (
        SELECT DISTINCT oi.product_id
        FROM order_items oi
        JOIN orders o
            ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
    ) x
        ON p.product_id = x.product_id
    WHERE p.discount_percent IS NOT NULL
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 4: Category Count",
    """
    SELECT COUNT(DISTINCT p.category) AS category_count
    FROM products p
    JOIN (
        SELECT DISTINCT oi.product_id
        FROM order_items oi
        JOIN orders o
            ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
    ) x
        ON p.product_id = x.product_id
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 5: Price Outlier Count",
    """
    SELECT COUNT(*) AS price_outlier_count
    FROM products p
    JOIN (
        SELECT DISTINCT oi.product_id
        FROM order_items oi
        JOIN orders o
            ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
    ) x
        ON p.product_id = x.product_id
    WHERE p.price_status = 'Outlier'
    """,
    [instamart_platform_id],
)

run_query(
    "Question 1: Which categories dominate Instamart's assortment?",
    """
    SELECT
        p.category,
        COUNT(DISTINCT p.product_id) AS products,
        SUM(COALESCE(oi.quantity, 0)) AS units_sold,
        ROUND(SUM(COALESCE(oi.line_total_inr, 0)), 2) AS item_value
    FROM products p
    JOIN order_items oi
        ON p.product_id = oi.product_id
    JOIN orders o
        ON oi.order_id = o.order_id
    WHERE o.platform_id = ?
    GROUP BY p.category
    ORDER BY item_value DESC
    """,
    [instamart_platform_id],
)

run_query(
    "Question 2: Which products are highly discounted?",
    """
    SELECT
        p.product_id,
        p.product_name,
        p.category,
        ROUND(p.mrp, 2) AS mrp,
        ROUND(p.selling_price, 2) AS selling_price,
        ROUND(p.discount_percent, 2) AS discount_percent
    FROM products p
    JOIN (
        SELECT DISTINCT oi.product_id
        FROM order_items oi
        JOIN orders o
            ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
    ) x
        ON p.product_id = x.product_id
    ORDER BY p.discount_percent DESC
    LIMIT 15
    """,
    [instamart_platform_id],
)

run_query(
    "Question 3: Which products have unusually high prices?",
    """
    SELECT
        p.product_id,
        p.product_name,
        p.category,
        ROUND(p.mrp, 2) AS mrp,
        ROUND(p.selling_price, 2) AS selling_price,
        ROUND(p.discount_percent, 2) AS discount_percent,
        p.price_status
    FROM products p
    JOIN (
        SELECT DISTINCT oi.product_id
        FROM order_items oi
        JOIN orders o
            ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
    ) x
        ON p.product_id = x.product_id
    WHERE p.selling_price IS NOT NULL
    ORDER BY p.selling_price DESC
    LIMIT 15
    """,
    [instamart_platform_id],
)

run_query(
    "Question 4: Which brands dominate Instamart?",
    """
    SELECT
        COALESCE(p.brand, 'Unknown') AS brand,
        COUNT(DISTINCT p.product_id) AS products,
        SUM(COALESCE(oi.quantity, 0)) AS units_sold,
        ROUND(SUM(COALESCE(oi.line_total_inr, 0)), 2) AS item_value
    FROM products p
    JOIN order_items oi
        ON p.product_id = oi.product_id
    JOIN orders o
        ON oi.order_id = o.order_id
    WHERE o.platform_id = ?
    GROUP BY COALESCE(p.brand, 'Unknown')
    ORDER BY products DESC, item_value DESC
    LIMIT 15
    """,
    [instamart_platform_id],
)

run_query(
    "Question 5: Which products drive basket value?",
    """
    SELECT
        p.product_id,
        p.product_name,
        p.category,
        SUM(COALESCE(oi.quantity, 0)) AS units_sold,
        ROUND(SUM(COALESCE(oi.line_total_inr, 0)), 2) AS item_value,
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
    GROUP BY p.product_id, p.product_name, p.category
    ORDER BY item_value DESC
    LIMIT 15
    """,
    [instamart_platform_id],
)


# ============================================================
# 5. INSTAMART — CUSTOMERS
# ============================================================

run_query(
    "KPI 1: Customers",
    """
    SELECT COUNT(DISTINCT customer_id) AS customers
    FROM orders
    WHERE platform_id = ?
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 2: Customer Growth",
    """
    SELECT
        SUBSTR(c.signup_date, 7, 4) AS year,
        COUNT(DISTINCT c.customer_id) AS new_customers
    FROM customers c
    WHERE LOWER(TRIM(c.signup_platform)) = 'swiggy instamart'
      AND c.signup_date IS NOT NULL
    GROUP BY SUBSTR(c.signup_date, 7, 4)
    ORDER BY year
    """,
)

run_query(
    "KPI 3: City Mix",
    """
    SELECT
        c.city,
        COUNT(DISTINCT c.customer_id) AS customers
    FROM customers c
    JOIN (
        SELECT DISTINCT customer_id
        FROM orders
        WHERE platform_id = ?
    ) x
        ON c.customer_id = x.customer_id
    GROUP BY c.city
    ORDER BY customers DESC
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 4: Signup Platform Mix",
    """
    SELECT
        COALESCE(c.signup_platform, 'Unknown') AS signup_platform,
        COUNT(DISTINCT c.customer_id) AS customers
    FROM customers c
    JOIN (
        SELECT DISTINCT customer_id
        FROM orders
        WHERE platform_id = ?
    ) x
        ON c.customer_id = x.customer_id
    GROUP BY COALESCE(c.signup_platform, 'Unknown')
    ORDER BY customers DESC
    """,
    [instamart_platform_id],
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
    ) x
        ON c.customer_id = x.customer_id
    GROUP BY COALESCE(c.app_version, 'Unknown')
    ORDER BY customers DESC
    """,
    [instamart_platform_id],
)

run_query(
    "Question 1: Which cities have the largest Instamart customer base?",
    """
    SELECT
        c.city,
        COUNT(DISTINCT c.customer_id) AS customers
    FROM customers c
    JOIN (
        SELECT DISTINCT customer_id
        FROM orders
        WHERE platform_id = ?
    ) x
        ON c.customer_id = x.customer_id
    GROUP BY c.city
    ORDER BY customers DESC
    """,
    [instamart_platform_id],
)

run_query(
    "Question 2: Where is customer acquisition weak?",
    """
    SELECT
        c.city,
        COUNT(DISTINCT c.customer_id) AS customers_acquired
    FROM customers c
    WHERE LOWER(TRIM(c.signup_platform)) = 'swiggy instamart'
    GROUP BY c.city
    ORDER BY customers_acquired ASC
    LIMIT 15
    """,
)

run_query(
    "Question 3: Which signup platform contributes most customers?",
    """
    SELECT
        COALESCE(c.signup_platform, 'Unknown') AS signup_platform,
        COUNT(DISTINCT c.customer_id) AS customers
    FROM customers c
    JOIN (
        SELECT DISTINCT customer_id
        FROM orders
        WHERE platform_id = ?
    ) x
        ON c.customer_id = x.customer_id
    GROUP BY COALESCE(c.signup_platform, 'Unknown')
    ORDER BY customers DESC
    LIMIT 1
    """,
    [instamart_platform_id],
)

run_query(
    "Question 4: Which cities have high customers but low transaction activity?",
    """
    WITH city_customers AS (
        SELECT
            c.city,
            COUNT(DISTINCT c.customer_id) AS customers
        FROM customers c
        JOIN (
            SELECT DISTINCT customer_id
            FROM orders
            WHERE platform_id = ?
        ) x
            ON c.customer_id = x.customer_id
        GROUP BY c.city
    ),
    city_orders AS (
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
            COALESCE(co.orders, 0) * 1.0
            / NULLIF(cc.customers, 0),
            2
        ) AS orders_per_customer
    FROM city_customers cc
    LEFT JOIN city_orders co
        ON cc.city = co.city
    ORDER BY orders_per_customer ASC
    LIMIT 15
    """,
    [instamart_platform_id, instamart_platform_id],
)

run_query(
    "Question 5: Is customer growth translating into order growth?",
    """
    WITH yearly_customers AS (
        SELECT
            SUBSTR(c.signup_date, 7, 4) AS year,
            COUNT(DISTINCT c.customer_id) AS new_customers
        FROM customers c
        WHERE LOWER(TRIM(c.signup_platform)) = 'swiggy instamart'
          AND c.signup_date IS NOT NULL
        GROUP BY SUBSTR(c.signup_date, 7, 4)
    ),
    yearly_orders AS (
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
    [instamart_platform_id],
)


# ============================================================
# 6. INSTAMART — ORDERS
# ============================================================

run_query(
    "KPI 1: Orders",
    """
    SELECT COUNT(*) AS orders
    FROM orders
    WHERE platform_id = ?
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 2: AOV",
    """
    SELECT ROUND(AVG(order_value_inr), 2) AS aov
    FROM orders
    WHERE platform_id = ?
      AND order_value_inr IS NOT NULL
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 3: Delivered %",
    """
    SELECT ROUND(
        SUM(
            CASE WHEN LOWER(order_status) = 'delivered'
                 THEN 1 ELSE 0 END
        ) * 100.0 / NULLIF(COUNT(*), 0),
        2
    ) AS delivered_percent
    FROM orders
    WHERE platform_id = ?
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 4: Cancellation %",
    """
    SELECT ROUND(
        SUM(
            CASE WHEN LOWER(order_status) = 'cancelled'
                 THEN 1 ELSE 0 END
        ) * 100.0 / NULLIF(COUNT(*), 0),
        2
    ) AS cancellation_percent
    FROM orders
    WHERE platform_id = ?
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 5: Return %",
    """
    SELECT ROUND(
        SUM(
            CASE WHEN LOWER(order_status) = 'returned'
                 THEN 1 ELSE 0 END
        ) * 100.0 / NULLIF(COUNT(*), 0),
        2
    ) AS return_percent
    FROM orders
    WHERE platform_id = ?
    """,
    [instamart_platform_id],
)

run_query(
    "Question 1: Which cities contribute most orders?",
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
    [instamart_platform_id],
)

run_query(
    "Question 2: Where are cancellation rates highest?",
    """
    SELECT
        ds.city,
        COUNT(o.order_id) AS orders,
        ROUND(
            SUM(
                CASE WHEN LOWER(o.order_status) = 'cancelled'
                     THEN 1 ELSE 0 END
            ) * 100.0 / NULLIF(COUNT(o.order_id), 0),
            2
        ) AS cancellation_rate_percent
    FROM orders o
    JOIN dark_stores ds
        ON o.store_id = ds.store_id
    WHERE o.platform_id = ?
    GROUP BY ds.city
    ORDER BY cancellation_rate_percent DESC
    """,
    [instamart_platform_id],
)

run_query(
    "Question 3: Where are returns highest?",
    """
    SELECT
        ds.city,
        COUNT(o.order_id) AS orders,
        SUM(
            CASE WHEN LOWER(o.order_status) = 'returned'
                 THEN 1 ELSE 0 END
        ) AS returned_orders,
        ROUND(
            SUM(
                CASE WHEN LOWER(o.order_status) = 'returned'
                     THEN 1 ELSE 0 END
            ) * 100.0 / NULLIF(COUNT(o.order_id), 0),
            2
        ) AS return_rate_percent
    FROM orders o
    JOIN dark_stores ds
        ON o.store_id = ds.store_id
    WHERE o.platform_id = ?
    GROUP BY ds.city
    ORDER BY return_rate_percent DESC
    """,
    [instamart_platform_id],
)

run_query(
    "Question 4: Which stores drive high order volume?",
    """
    SELECT
        o.store_id,
        ds.city,
        COUNT(o.order_id) AS orders,
        ROUND(SUM(COALESCE(o.order_value_inr, 0)), 2) AS revenue
    FROM orders o
    JOIN dark_stores ds
        ON o.store_id = ds.store_id
    WHERE o.platform_id = ?
    GROUP BY o.store_id, ds.city
    ORDER BY orders DESC
    LIMIT 15
    """,
    [instamart_platform_id],
)

run_query(
    "Question 5: What would most improve successful order completion?",
    """
    SELECT
        ds.city,
        COUNT(o.order_id) AS total_orders,
        SUM(
            CASE WHEN LOWER(o.order_status) = 'delivered'
                 THEN 1 ELSE 0 END
        ) AS delivered_orders,
        SUM(
            CASE WHEN LOWER(o.order_status) IN ('cancelled', 'returned')
                 THEN 1 ELSE 0 END
        ) AS failed_orders,
        ROUND(
            SUM(
                CASE WHEN LOWER(o.order_status) = 'delivered'
                     THEN 1 ELSE 0 END
            ) * 100.0 / NULLIF(COUNT(o.order_id), 0),
            2
        ) AS completion_rate_percent
    FROM orders o
    JOIN dark_stores ds
        ON o.store_id = ds.store_id
    WHERE o.platform_id = ?
    GROUP BY ds.city
    ORDER BY completion_rate_percent ASC, total_orders DESC
    """,
    [instamart_platform_id],
)


# ============================================================
# 7. INSTAMART — ORDER ITEMS
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
    [instamart_platform_id],
)

run_query(
    "KPI 2: Item Value",
    """
    SELECT ROUND(
        SUM(COALESCE(oi.line_total_inr, 0)),
        2
    ) AS item_value
    FROM order_items oi
    JOIN orders o
        ON oi.order_id = o.order_id
    WHERE o.platform_id = ?
    """,
    [instamart_platform_id],
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
    [instamart_platform_id],
)

run_query(
    "KPI 4: Basket Size",
    """
    SELECT ROUND(
        SUM(COALESCE(oi.quantity, 0)) * 1.0
        / NULLIF(COUNT(DISTINCT oi.order_id), 0),
        2
    ) AS average_basket_size
    FROM order_items oi
    JOIN orders o
        ON oi.order_id = o.order_id
    WHERE o.platform_id = ?
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 5: Product Contribution",
    """
    WITH product_value AS (
        SELECT
            p.product_id,
            SUM(COALESCE(oi.line_total_inr, 0)) AS item_value
        FROM order_items oi
        JOIN orders o
            ON oi.order_id = o.order_id
        JOIN products p
            ON oi.product_id = p.product_id
        WHERE o.platform_id = ?
        GROUP BY p.product_id
    )
    SELECT ROUND(
        MAX(item_value) * 100.0
        / NULLIF(SUM(item_value), 0),
        2
    ) AS top_product_contribution_percent
    FROM product_value
    """,
    [instamart_platform_id],
)

run_query(
    "Question 1: Which products sell the most units?",
    """
    SELECT
        p.product_id,
        p.product_name,
        p.category,
        SUM(COALESCE(oi.quantity, 0)) AS units_sold
    FROM order_items oi
    JOIN orders o
        ON oi.order_id = o.order_id
    JOIN products p
        ON oi.product_id = p.product_id
    WHERE o.platform_id = ?
    GROUP BY p.product_id, p.product_name, p.category
    ORDER BY units_sold DESC
    LIMIT 15
    """,
    [instamart_platform_id],
)

run_query(
    "Question 2: Which products create the most value?",
    """
    SELECT
        p.product_id,
        p.product_name,
        p.category,
        SUM(COALESCE(oi.quantity, 0)) AS units_sold,
        ROUND(SUM(COALESCE(oi.line_total_inr, 0)), 2) AS item_value
    FROM order_items oi
    JOIN orders o
        ON oi.order_id = o.order_id
    JOIN products p
        ON oi.product_id = p.product_id
    WHERE o.platform_id = ?
    GROUP BY p.product_id, p.product_name, p.category
    ORDER BY item_value DESC
    LIMIT 15
    """,
    [instamart_platform_id],
)

run_query(
    "Question 3: Which categories dominate customer baskets?",
    """
    SELECT
        p.category,
        SUM(COALESCE(oi.quantity, 0)) AS units_sold,
        COUNT(DISTINCT oi.order_id) AS orders_containing_category,
        ROUND(
            SUM(COALESCE(oi.line_total_inr, 0)),
            2
        ) AS item_value
    FROM order_items oi
    JOIN orders o
        ON oi.order_id = o.order_id
    JOIN products p
        ON oi.product_id = p.product_id
    WHERE o.platform_id = ?
    GROUP BY p.category
    ORDER BY item_value DESC
    """,
    [instamart_platform_id],
)

run_query(
    "Question 4: Which products have high repeat demand signals?",
    """
    WITH customer_product_orders AS (
        SELECT
            o.customer_id,
            oi.product_id,
            COUNT(DISTINCT oi.order_id) AS order_count
        FROM order_items oi
        JOIN orders o
            ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
        GROUP BY o.customer_id, oi.product_id
    ),
    product_repeat AS (
        SELECT
            product_id,
            SUM(
                CASE WHEN order_count > 1 THEN 1 ELSE 0 END
            ) AS repeat_customers
        FROM customer_product_orders
        GROUP BY product_id
    )
    SELECT
        p.product_id,
        p.product_name,
        p.category,
        COALESCE(pr.repeat_customers, 0) AS repeat_customers,
        SUM(COALESCE(oi.quantity, 0)) AS units_sold
    FROM order_items oi
    JOIN orders o
        ON oi.order_id = o.order_id
    JOIN products p
        ON oi.product_id = p.product_id
    LEFT JOIN product_repeat pr
        ON p.product_id = pr.product_id
    WHERE o.platform_id = ?
    GROUP BY
        p.product_id,
        p.product_name,
        p.category,
        pr.repeat_customers
    ORDER BY repeat_customers DESC, units_sold DESC
    LIMIT 15
    """,
    [instamart_platform_id, instamart_platform_id],
)

run_query(
    "Question 5: How can Instamart increase basket value?",
    """
    SELECT
        p.category,
        COUNT(DISTINCT oi.order_id) AS orders,
        ROUND(
            SUM(COALESCE(oi.line_total_inr, 0)),
            2
        ) AS item_value,
        ROUND(
            SUM(COALESCE(oi.line_total_inr, 0))
            / NULLIF(COUNT(DISTINCT oi.order_id), 0),
            2
        ) AS value_per_order
    FROM order_items oi
    JOIN orders o
        ON oi.order_id = o.order_id
    JOIN products p
        ON oi.product_id = p.product_id
    WHERE o.platform_id = ?
    GROUP BY p.category
    ORDER BY value_per_order DESC
    """,
    [instamart_platform_id],
)


# ============================================================
# 8. INSTAMART — INVENTORY
# ============================================================

run_query(
    "KPI 1: Stock Units",
    """
    SELECT SUM(COALESCE(i.stock_units, 0)) AS stock_units
    FROM inventory i
    JOIN dark_stores ds
        ON i.store_id = ds.store_id
    WHERE ds.platform_id = ?
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 2: Low-stock SKUs",
    """
    SELECT COUNT(*) AS low_stock_skus
    FROM inventory i
    JOIN dark_stores ds
        ON i.store_id = ds.store_id
    WHERE ds.platform_id = ?
      AND COALESCE(i.stock_units, 0)
          <= COALESCE(i.reorder_level, 0)
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 3: Reorder Risk",
    """
    SELECT ROUND(
        SUM(
            CASE
                WHEN COALESCE(i.stock_units, 0)
                     < COALESCE(i.reorder_level, 0)
                THEN 1 ELSE 0
            END
        ) * 100.0 / NULLIF(COUNT(*), 0),
        2
    ) AS reorder_risk_percent
    FROM inventory i
    JOIN dark_stores ds
        ON i.store_id = ds.store_id
    WHERE ds.platform_id = ?
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 4: Expiry Risk",
    """
    SELECT SUM(COALESCE(i.stock_units, 0)) AS expiry_risk_units
    FROM inventory i
    JOIN dark_stores ds
        ON i.store_id = ds.store_id
    WHERE ds.platform_id = ?
      AND i.expiry_date IS NOT NULL
      AND DATE(i.expiry_date) <= DATE('now', '+30 day')
      AND COALESCE(i.stock_units, 0) > 0
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 5: Stock per Store",
    """
    SELECT ROUND(
        SUM(COALESCE(i.stock_units, 0)) * 1.0
        / NULLIF(COUNT(DISTINCT ds.store_id), 0),
        2
    ) AS stock_per_store
    FROM inventory i
    JOIN dark_stores ds
        ON i.store_id = ds.store_id
    WHERE ds.platform_id = ?
    """,
    [instamart_platform_id],
)

run_query(
    "Question 1: Which stores have the highest stockout risk?",
    """
    SELECT
        ds.store_id,
        ds.city,
        COUNT(*) AS total_skus,
        SUM(
            CASE
                WHEN COALESCE(i.stock_units, 0)
                     < COALESCE(i.reorder_level, 0)
                THEN 1 ELSE 0
            END
        ) AS low_stock_skus,
        ROUND(
            SUM(
                CASE
                    WHEN COALESCE(i.stock_units, 0)
                         < COALESCE(i.reorder_level, 0)
                    THEN 1 ELSE 0
                END
            ) * 100.0 / NULLIF(COUNT(*), 0),
            2
        ) AS stockout_risk_percent
    FROM inventory i
    JOIN dark_stores ds
        ON i.store_id = ds.store_id
    WHERE ds.platform_id = ?
    GROUP BY ds.store_id, ds.city
    ORDER BY stockout_risk_percent DESC
    LIMIT 15
    """,
    [instamart_platform_id],
)

run_query(
    "Question 2: Which products are below reorder levels?",
    """
    SELECT
        i.product_id,
        p.product_name,
        ds.store_id,
        ds.city,
        ROUND(i.stock_units, 2) AS stock_units,
        ROUND(i.reorder_level, 2) AS reorder_level,
        ROUND(i.reorder_level - i.stock_units, 2) AS shortage
    FROM inventory i
    JOIN dark_stores ds
        ON i.store_id = ds.store_id
    JOIN products p
        ON i.product_id = p.product_id
    WHERE ds.platform_id = ?
      AND COALESCE(i.stock_units, 0)
          < COALESCE(i.reorder_level, 0)
    ORDER BY shortage DESC
    LIMIT 20
    """,
    [instamart_platform_id],
)

run_query(
    "Question 3: Where is inventory excessive?",
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
    [instamart_platform_id],
)

run_query(
    "Question 4: Which products face expiry risk?",
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
    [instamart_platform_id],
)

run_query(
    "Question 5: Where is cash tied up in inventory?",
    """
    SELECT
        ds.store_id,
        ds.city,
        ROUND(
            SUM(
                CASE
                    WHEN COALESCE(i.stock_units, 0)
                         > COALESCE(i.reorder_level, 0)
                    THEN
                        (i.stock_units - i.reorder_level)
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
    [instamart_platform_id],
)


# ============================================================
# 9. INSTAMART — LOGISTICS
# ============================================================

run_query(
    "KPI 1: Delay Rate",
    """
    SELECT ROUND(
        SUM(
            CASE
                WHEN LOWER(l.delay_flag) IN ('yes', 'y')
                THEN 1 ELSE 0
            END
        ) * 100.0 / NULLIF(COUNT(*), 0),
        2
    ) AS delay_rate_percent
    FROM logistics l
    JOIN orders o
        ON l.order_id = o.order_id
    WHERE o.platform_id = ?
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 2: Delivery Rating",
    """
    SELECT ROUND(AVG(l.delivery_rating), 2) AS delivery_rating
    FROM logistics l
    JOIN orders o
        ON l.order_id = o.order_id
    WHERE o.platform_id = ?
      AND l.delivery_rating IS NOT NULL
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 3: Average Distance",
    """
    SELECT ROUND(AVG(l.distance_km), 2) AS average_distance_km
    FROM logistics l
    JOIN orders o
        ON l.order_id = o.order_id
    WHERE o.platform_id = ?
      AND l.distance_km IS NOT NULL
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 4: Delayed Orders",
    """
    SELECT COUNT(*) AS delayed_orders
    FROM logistics l
    JOIN orders o
        ON l.order_id = o.order_id
    WHERE o.platform_id = ?
      AND LOWER(l.delay_flag) IN ('yes', 'y')
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 5: Vehicle Mix",
    """
    SELECT
        l.vehicle_type,
        COUNT(*) AS deliveries,
        ROUND(
            COUNT(*) * 100.0
            / SUM(COUNT(*)) OVER (),
            2
        ) AS vehicle_mix_percent
    FROM logistics l
    JOIN orders o
        ON l.order_id = o.order_id
    WHERE o.platform_id = ?
    GROUP BY l.vehicle_type
    ORDER BY deliveries DESC
    """,
    [instamart_platform_id],
)

run_query(
    "Question 1: Which cities experience the most delays?",
    """
    SELECT
        ds.city,
        COUNT(l.delivery_id) AS deliveries,
        SUM(
            CASE
                WHEN LOWER(l.delay_flag) IN ('yes', 'y')
                THEN 1 ELSE 0
            END
        ) AS delayed_deliveries,
        ROUND(
            SUM(
                CASE
                    WHEN LOWER(l.delay_flag) IN ('yes', 'y')
                    THEN 1 ELSE 0
                END
            ) * 100.0 / NULLIF(COUNT(l.delivery_id), 0),
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
    [instamart_platform_id],
)

run_query(
    "Question 2: Which vehicle types perform best?",
    """
    SELECT
        l.vehicle_type,
        COUNT(*) AS deliveries,
        ROUND(AVG(l.distance_km), 2) AS average_distance_km,
        ROUND(
            SUM(
                CASE
                    WHEN LOWER(l.delay_flag) IN ('yes', 'y')
                    THEN 1 ELSE 0
                END
            ) * 100.0 / NULLIF(COUNT(*), 0),
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
    [instamart_platform_id],
)

run_query(
    "Question 3: Does longer distance reduce delivery performance?",
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
            SUM(
                CASE
                    WHEN LOWER(l.delay_flag) IN ('yes', 'y')
                    THEN 1 ELSE 0
                END
            ) * 100.0 / NULLIF(COUNT(*), 0),
            2
        ) AS delay_rate_percent,
        ROUND(AVG(l.delivery_rating), 2) AS average_rating
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
    [instamart_platform_id],
)

run_query(
    "Question 4: Which stores are linked to high delay rates?",
    """
    SELECT
        o.store_id,
        ds.city,
        COUNT(l.delivery_id) AS deliveries,
        ROUND(
            SUM(
                CASE
                    WHEN LOWER(l.delay_flag) IN ('yes', 'y')
                    THEN 1 ELSE 0
                END
            ) * 100.0 / NULLIF(COUNT(l.delivery_id), 0),
            2
        ) AS delay_rate_percent
    FROM logistics l
    JOIN orders o
        ON l.order_id = o.order_id
    JOIN dark_stores ds
        ON o.store_id = ds.store_id
    WHERE o.platform_id = ?
    GROUP BY o.store_id, ds.city
    HAVING COUNT(l.delivery_id) >= 10
    ORDER BY delay_rate_percent DESC
    LIMIT 15
    """,
    [instamart_platform_id],
)

run_query(
    "Question 5: How can delivery reliability be improved?",
    """
    SELECT
        SUBSTR(o.order_datetime, 1, 7) AS month,
        COUNT(l.delivery_id) AS deliveries,
        SUM(
            CASE
                WHEN LOWER(l.delay_flag) IN ('yes', 'y')
                THEN 1 ELSE 0
            END
        ) AS delayed_deliveries,
        ROUND(
            SUM(
                CASE
                    WHEN LOWER(l.delay_flag) IN ('yes', 'y')
                    THEN 1 ELSE 0
                END
            ) * 100.0 / NULLIF(COUNT(l.delivery_id), 0),
            2
        ) AS delay_rate_percent,
        ROUND(AVG(l.delivery_rating), 2) AS average_rating
    FROM logistics l
    JOIN orders o
        ON l.order_id = o.order_id
    WHERE o.platform_id = ?
    GROUP BY SUBSTR(o.order_datetime, 1, 7)
    ORDER BY month
    """,
    [instamart_platform_id],
)


# ============================================================
# 10. INSTAMART — MONTHLY P&L
# ============================================================

run_query(
    "KPI 1: Revenue",
    """
    SELECT ROUND(SUM(revenue_inr), 2) AS revenue
    FROM pnl_monthly_safe
    WHERE platform_id = ?
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 2: COGS",
    """
    SELECT ROUND(SUM(cogs_inr), 2) AS cogs
    FROM pnl_monthly_safe
    WHERE platform_id = ?
    """,
    [instamart_platform_id],
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
    [instamart_platform_id],
)

run_query(
    "KPI 4: Profit",
    """
    SELECT ROUND(SUM(profit_inr), 2) AS profit
    FROM pnl_monthly_safe
    WHERE platform_id = ?
    """,
    [instamart_platform_id],
)

run_query(
    "KPI 5: Margin %",
    """
    SELECT ROUND(
        SUM(profit_inr) * 100.0
        / NULLIF(SUM(revenue_inr), 0),
        2
    ) AS margin_percent
    FROM pnl_monthly_safe
    WHERE platform_id = ?
    """,
    [instamart_platform_id],
)

run_query(
    "Question 1: Which cities are most profitable?",
    """
    SELECT
        city,
        ROUND(SUM(revenue_inr), 2) AS revenue,
        ROUND(SUM(profit_inr), 2) AS profit,
        ROUND(
            SUM(profit_inr) * 100.0
            / NULLIF(SUM(revenue_inr), 0),
            2
        ) AS margin_percent
    FROM pnl_monthly_safe
    WHERE platform_id = ?
    GROUP BY city
    ORDER BY profit DESC
    """,
    [instamart_platform_id],
)

run_query(
    "Question 2: Which cities have poor margins?",
    """
    SELECT
        city,
        ROUND(SUM(revenue_inr), 2) AS revenue,
        ROUND(SUM(profit_inr), 2) AS profit,
        ROUND(
            SUM(profit_inr) * 100.0
            / NULLIF(SUM(revenue_inr), 0),
            2
        ) AS margin_percent
    FROM pnl_monthly_safe
    WHERE platform_id = ?
    GROUP BY city
    HAVING margin_percent < 10
    ORDER BY margin_percent ASC
    """,
    [instamart_platform_id],
)

run_query(
    "Question 3: Which cost category is growing fastest?",
    """
    SELECT
        month,
        ROUND(SUM(cogs_inr), 2) AS cogs,
        ROUND(SUM(delivery_cost_inr), 2) AS delivery_cost,
        ROUND(SUM(marketing_spend_inr), 2) AS marketing_spend,
        ROUND(SUM(employee_cost_inr), 2) AS employee_cost,
        ROUND(SUM(other_opex_inr), 2) AS other_opex
    FROM pnl_monthly_safe
    WHERE platform_id = ?
    GROUP BY month
    ORDER BY month
    """,
    [instamart_platform_id],
)

run_query(
    "Question 4: Is marketing spend generating sufficient revenue?",
    """
    SELECT
        month,
        ROUND(revenue_inr, 2) AS revenue,
        ROUND(marketing_spend_inr, 2) AS marketing_spend,
        ROUND(
            revenue_inr / NULLIF(marketing_spend_inr, 0),
            2
        ) AS revenue_per_marketing_rupee,
        CASE
            WHEN revenue_inr / NULLIF(marketing_spend_inr, 0) >= 5
                THEN 'Efficient'
            WHEN revenue_inr / NULLIF(marketing_spend_inr, 0) >= 2
                THEN 'Moderate'
            ELSE 'Low Efficiency'
        END AS marketing_status
    FROM pnl_monthly_safe
    WHERE platform_id = ?
    ORDER BY month
    """,
    [instamart_platform_id],
)

run_query(
    "Question 5: How is profitability changing monthly?",
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
        ) AS margin_percent
    FROM pnl_monthly_safe
    WHERE platform_id = ?
    GROUP BY month
    ORDER BY month
    """,
    [instamart_platform_id],
)


