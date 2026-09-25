# ============================================================
# STEP 1: IMPORT LIBRARIES
# ============================================================

import os
import sqlite3

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

try:
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False


# ============================================================
# STEP 2: PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Quick Commerce Analytics Command Center",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# STEP 3: FIND SQLITE DATABASE
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATABASE_CANDIDATES = [
    os.path.join(
        BASE_DIR,
        "database",
        "quick_commerce.db",
    ),
    os.path.join(
        os.path.dirname(BASE_DIR),
        "database",
        "quick_commerce.db",
    ),
]

DATABASE_PATH = next(
    (
        path
        for path in DATABASE_CANDIDATES
        if os.path.exists(path)
    ),
    DATABASE_CANDIDATES[0],
)

if not os.path.exists(DATABASE_PATH):
    st.error(
        "SQLite database not found. Put this dashboard inside "
        "SDLC Main and make sure database/quick_commerce.db exists."
    )
    st.stop()

# ============================================================
# STEP 4: CREATE A WRITABLE RUNTIME DATABASE
# ============================================================
# Keep the repository database unchanged.
# Load a complete copy into an in-memory SQLite database so the
# dashboard can safely create views and helper columns at runtime.

@st.cache_resource
def get_connection(source_database_path):

    source_connection = sqlite3.connect(
        source_database_path,
        check_same_thread=False,
    )

    runtime_connection = sqlite3.connect(
        ":memory:",
        check_same_thread=False,
    )

    source_connection.backup(
        runtime_connection
    )

    source_connection.close()

    return runtime_connection


# ============================================================
# STEP 5: SQLITE CONNECTION
# ============================================================

conn = get_connection(
    DATABASE_PATH
)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_data(query, params=()):
    try:
        result = pd.read_sql_query(
            query,
            conn,
            params=list(params),
        )

        # Plotly requires unique DataFrame column names.
        result = result.loc[:, ~result.columns.duplicated()].copy()
        result.columns = [str(column) for column in result.columns]
        return result

    except Exception as error:
        st.error(f"Query could not be loaded: {error}")
        return pd.DataFrame()


# ============================================================
# STEP 5: VERIFY REQUIRED TABLES
# ============================================================

required_tables = [
    "platforms",
    "dark_stores",
    "employees",
    "products",
    "customers",
    "orders",
    "order_items",
    "inventory",
    "logistics",
    "pnl_monthly",
]

existing_tables = set(
    fetch_data(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        """
    )["name"].tolist()
)

missing_tables = [
    table
    for table in required_tables
    if table not in existing_tables
]

if missing_tables:
    st.error(
        "Missing SQLite tables: "
        + ", ".join(missing_tables)
    )
    st.stop()


# ============================================================
# STEP 5B: ENSURE DASHBOARD HELPER COLUMNS
# ============================================================
# Older SQLite databases may not contain the helper columns that
# appear in the finalized platform analysis files.

dark_store_columns = fetch_data(
    "PRAGMA table_info(dark_stores)"
)

existing_dark_store_columns = set()

if not dark_store_columns.empty and "name" in dark_store_columns.columns:
    existing_dark_store_columns = set(
        dark_store_columns["name"].astype(str).tolist()
    )

if "store_name_clean" not in existing_dark_store_columns:
    conn.execute(
        "ALTER TABLE dark_stores ADD COLUMN store_name_clean TEXT"
    )
    conn.execute(
        "UPDATE dark_stores SET store_name_clean = store_name"
    )

if "city_clean" not in existing_dark_store_columns:
    conn.execute(
        "ALTER TABLE dark_stores ADD COLUMN city_clean TEXT"
    )
    conn.execute(
        "UPDATE dark_stores SET city_clean = city"
    )


# Ensure employee helper column exists for databases created by earlier analysis scripts.
employee_columns = fetch_data(
    "PRAGMA table_info(employees)"
)

existing_employee_columns = set()

if not employee_columns.empty and "name" in employee_columns.columns:
    existing_employee_columns = set(
        employee_columns["name"].astype(str).tolist()
    )

if "work_status" not in existing_employee_columns:
    conn.execute(
        "ALTER TABLE employees ADD COLUMN work_status TEXT"
    )

    if "employment_status" in existing_employee_columns:
        conn.execute(
            """
            UPDATE employees
            SET work_status = CASE
                WHEN LOWER(TRIM(employment_status)) IN ('active', 'working')
                    THEN 'Currently Working'
                WHEN LOWER(TRIM(employment_status)) = 'on leave'
                    THEN 'On Leave'
                WHEN LOWER(TRIM(employment_status)) IN ('resigned', 'terminated')
                    THEN 'Not Working'
                ELSE 'Unknown'
            END
            """
        )
    else:
        conn.execute(
            "UPDATE employees SET work_status = 'Unknown'"
        )

conn.commit()


# ============================================================
# STEP 6: CREATE SAFE P&L VIEW
# ============================================================
# The object name may already exist as a table or a view because
# the SQLite database is rebuilt by the analysis scripts.
# Detect the existing object type and remove it safely before
# creating the finalized view.

existing_pnl_object = conn.execute(
    """
    SELECT type
    FROM sqlite_master
    WHERE name = 'pnl_monthly_safe'
    """
).fetchone()


if existing_pnl_object:

    existing_object_type = existing_pnl_object[0]

    if existing_object_type == "view":

        conn.execute(
            "DROP VIEW pnl_monthly_safe"
        )

    elif existing_object_type == "table":

        conn.execute(
            "DROP TABLE pnl_monthly_safe"
        )

    elif existing_object_type == "index":

        conn.execute(
            "DROP INDEX pnl_monthly_safe"
        )

    elif existing_object_type == "trigger":

        conn.execute(
            "DROP TRIGGER pnl_monthly_safe"
        )


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
# STEP 7: PLATFORM CONFIGURATION
# ============================================================

platform_df = fetch_data(
    """
    SELECT
        platform_id,
        platform_name
    FROM platforms
    ORDER BY platform_id
    """
)

PLATFORM_ORDER = [
    "Zepto",
    "Blinkit",
    "Swiggy Instamart",
    "BigBasket",
]

PLATFORM_THEMES = {
    "zepto": {
        "primary": "#8B5CF6",
        "secondary": "#D946EF",
        "accent": "#C084FC",
        "dark": "#0A0810",
        "panel": "#17111F",
        "sidebar": "#100B18",
        "icon": "🟣",
    },
    "blinkit": {
        "primary": "#FACC15",
        "secondary": "#F59E0B",
        "accent": "#FDE047",
        "dark": "#0D0B05",
        "panel": "#1B170B",
        "sidebar": "#110F07",
        "icon": "🟡",
    },
    "swiggy instamart": {
        "primary": "#FF6B00",
        "secondary": "#F59E0B",
        "accent": "#FDBA74",
        "dark": "#0D0905",
        "panel": "#1A120B",
        "sidebar": "#120B07",
        "icon": "🟠",
    },
    "bigbasket": {
        "primary": "#22C55E",
        "secondary": "#16A34A",
        "accent": "#86EFAC",
        "dark": "#071008",
        "panel": "#0E1A12",
        "sidebar": "#09120C",
        "icon": "🟢",
    },
    "big basket": {
        "primary": "#22C55E",
        "secondary": "#16A34A",
        "accent": "#86EFAC",
        "dark": "#071008",
        "panel": "#0E1A12",
        "sidebar": "#09120C",
        "icon": "🟢",
    },
}


def get_theme(platform_name):
    return PLATFORM_THEMES.get(
        str(platform_name).strip().lower(),
        PLATFORM_THEMES["zepto"],
    )


# ============================================================
# STEP 8: SIDEBAR FILTER VALUES
# ============================================================

cities = fetch_data(
    """
    SELECT DISTINCT
        city_clean AS city
    FROM dark_stores
    WHERE city_clean IS NOT NULL
    ORDER BY city_clean
    """
)["city"].dropna().astype(str).tolist()

categories = fetch_data(
    """
    SELECT DISTINCT category
    FROM products
    WHERE category IS NOT NULL
    ORDER BY category
    """
)["category"].dropna().astype(str).tolist()


# Product names used by the Product slicer.
products = fetch_data(
    """
    SELECT DISTINCT product_name
    FROM products
    WHERE product_name IS NOT NULL
    ORDER BY product_name
    """
)["product_name"].dropna().astype(str).tolist()

years = fetch_data(
    """
    SELECT DISTINCT
        strftime('%Y', order_datetime) AS year
    FROM orders
    WHERE order_datetime IS NOT NULL
    ORDER BY year
    """
)["year"].dropna().astype(str).tolist()

statuses = fetch_data(
    """
    SELECT DISTINCT order_status
    FROM orders
    WHERE order_status IS NOT NULL
    ORDER BY order_status
    """
)["order_status"].dropna().astype(str).tolist()

payments = fetch_data(
    """
    SELECT DISTINCT payment_mode
    FROM orders
    WHERE payment_mode IS NOT NULL
    ORDER BY payment_mode
    """
)["payment_mode"].dropna().astype(str).tolist()

vehicles = fetch_data(
    """
    SELECT DISTINCT vehicle_type
    FROM logistics
    WHERE vehicle_type IS NOT NULL
    ORDER BY vehicle_type
    """
)["vehicle_type"].dropna().astype(str).tolist()

date_range_df = fetch_data(
    """
    SELECT
        MIN(date(order_datetime)) AS min_date,
        MAX(date(order_datetime)) AS max_date
    FROM orders
    """
)

min_date = pd.to_datetime(
    date_range_df.loc[0, "min_date"]
).date()

max_date = pd.to_datetime(
    date_range_df.loc[0, "max_date"]
).date()


# ============================================================
# STEP 9: SIDEBAR
# ============================================================

platform_names = platform_df["platform_name"].tolist()

ordered_platforms = [
    name
    for name in PLATFORM_ORDER
    if name in platform_names
]

if not ordered_platforms:
    ordered_platforms = platform_names

with st.sidebar:

    st.markdown(
        """
        <div class="brand-block">
            <div class="brand-name">Quick Commerce</div>
            <div class="brand-subtitle">
                Executive Analytics Command Center
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    selected_platform = st.selectbox(
        "Platform",
        ordered_platforms,
        index=0,
    )

    selected_platform_id = int(
        platform_df.loc[
            platform_df["platform_name"] == selected_platform,
            "platform_id",
        ].iloc[0]
    )

    theme = get_theme(selected_platform)

    st.markdown(
        f"""
        <div class="active-platform">
            <span class="platform-dot"></span>
            {theme["icon"]} {selected_platform}
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Dashboard Section")

    dashboard_sections = [
        "Overview",
        "Store",
        "Employee",
        "Product",
        "Customer",
        "Orders",
        "Order Items",
        "Inventory",
        "Logistics",
        "Monthly P&L",
    ]

    selected_section = st.radio(
        "Dashboard Section",
        dashboard_sections,
        index=0,
    )

    st.markdown("---")
    st.markdown("### Slicers")

    selected_city = st.multiselect(
        "City",
        ["All"] + cities,
        default=["All"],
    )

    selected_year = st.multiselect(
        "Order Year",
        ["All"] + years,
        default=["All"],
    )

    selected_date_range = st.date_input(
        "Order Date",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )

    selected_category = st.multiselect(
        "Category",
        ["All"] + categories,
        default=["All"],
    )

    selected_product = st.multiselect(
        "Product",
        ["All"] + products,
        default=["All"],
    )

    selected_status = st.multiselect(
        "Order Status",
        ["All"] + statuses,
        default=["All"],
    )

    selected_payment = st.multiselect(
        "Payment Mode",
        ["All"] + payments,
        default=["All"],
    )

    selected_vehicle = st.multiselect(
        "Vehicle Type",
        ["All"] + vehicles,
        default=["All"],
    )


# ============================================================
# STEP 10: DATE RANGE NORMALIZATION
# ============================================================

if isinstance(selected_date_range, tuple):
    if len(selected_date_range) == 2:
        start_date, end_date = selected_date_range
    else:
        start_date = selected_date_range[0]
        end_date = selected_date_range[0]
else:
    start_date = selected_date_range
    end_date = selected_date_range


# ============================================================
# STEP 11: MODERN DARK CSS
# ============================================================

st.markdown(
    f"""
    <style>

    .stApp {{
        background:
            radial-gradient(circle at 8% 0%, {theme["primary"]}24, transparent 28%),
            radial-gradient(circle at 95% 5%, {theme["secondary"]}18, transparent 25%),
            {theme["dark"]};
        color: #F7F3FB;
    }}

    .block-container {{
        max-width: 1500px;
        padding-top: 1.35rem;
        padding-bottom: 2.5rem;
    }}

    section[data-testid="stSidebar"] {{
        background: linear-gradient(180deg, {theme["sidebar"]} 0%, {theme["dark"]} 100%);
        border-right: 1px solid {theme["primary"]}2C;
    }}

    section[data-testid="stSidebar"] * {{
        color: #EEE8F6;
    }}

    .brand-block {{
        padding: 6px 0 17px;
    }}

    .brand-name {{
        font-size: 25px;
        font-weight: 850;
        letter-spacing: -.5px;
    }}

    .brand-subtitle {{
        color: #A89CB4;
        font-size: 12px;
        margin-top: 3px;
    }}

    .active-platform {{
        margin: 4px 0 18px;
        padding: 10px 12px;
        border-radius: 12px;
        border: 1px solid {theme["primary"]}42;
        background: linear-gradient(135deg, {theme["primary"]}18, rgba(255,255,255,.02));
        font-size: 13px;
        font-weight: 750;
    }}

    .platform-dot {{
        display: inline-block;
        width: 9px;
        height: 9px;
        margin-right: 8px;
        border-radius: 50%;
        background: {theme["primary"]};
        box-shadow: 0 0 12px {theme["primary"]};
    }}

    .hero {{
        border: 1px solid {theme["primary"]}38;
        border-radius: 24px;
        padding: 24px 28px;
        margin-bottom: 21px;
        background: linear-gradient(135deg, {theme["primary"]}2C, {theme["secondary"]}10);
        box-shadow: 0 18px 55px rgba(0,0,0,.27), inset 0 1px 0 rgba(255,255,255,.04);
    }}

    .hero-title {{
        font-size: 32px;
        font-weight: 850;
        letter-spacing: -.8px;
        color: #FFFFFF;
    }}

    .hero-subtitle {{
        color: #C8BDD2;
        font-size: 13px;
        margin-top: 7px;
    }}

    .section-title {{
        font-size: 23px;
        font-weight: 820;
        color: #FFFFFF;
        margin-top: 10px;
        margin-bottom: 4px;
    }}

    .section-subtitle {{
        color: #AFA3B9;
        font-size: 12px;
        margin-bottom: 16px;
    }}

    .stPlotlyChart {{
        margin-bottom: 18px;
    }}

    .stPlotlyChart > div {{
        min-height: 400px;
    }}

    .question-card {{
        padding: 11px 15px;
        margin-top: 16px;
        margin-bottom: 9px;
        border-left: 3px solid {theme["primary"]};
        border-radius: 0 10px 10px 0;
        background: rgba(255,255,255,.025);
        color: #F5F0F8;
        font-size: 13px;
        font-weight: 760;
    }}

    [data-testid="stMetric"] {{
        background: linear-gradient(145deg, rgba(255,255,255,.035), {theme["primary"]}09);
        border: 1px solid {theme["primary"]}2F;
        border-radius: 16px;
        padding: 14px 16px;
        min-height: 118px;
        box-shadow: 0 14px 34px rgba(0,0,0,.20), inset 0 1px 0 rgba(255,255,255,.03);
    }}

    [data-testid="stMetricLabel"] {{
        color: #AAA0B3 !important;
        font-size: 11px !important;
        font-weight: 800 !important;
        text-transform: uppercase;
        letter-spacing: .75px;
    }}

    [data-testid="stMetricValue"] {{
        color: #FFFFFF !important;
        font-size: 27px !important;
        font-weight: 850 !important;
    }}

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# STEP 12: FILTER RESULT DATA
# ============================================================

def apply_dashboard_filters(df):
    if df is None or df.empty:
        return df

    result = df.copy()

    if selected_city and "All" not in selected_city:
        city_column = next(
            (
                column
                for column in ["city", "city_clean"]
                if column in result.columns
            ),
            None,
        )

        if city_column:
            result = result[
                result[city_column].astype(str).isin(selected_city)
            ]

    if (
        selected_category
        and "All" not in selected_category
        and "category" in result.columns
    ):
        result = result[
            result["category"].astype(str).isin(selected_category)
        ]

    # Apply Product slicer when the query returns product-level data.
    if selected_product and "All" not in selected_product:
        product_column = next(
            (
                column
                for column in ["product_name", "product"]
                if column in result.columns
            ),
            None,
        )

        if product_column:
            result = result[
                result[product_column].astype(str).isin(selected_product)
            ]

    if selected_year and "All" not in selected_year:
        year_values = [
            str(value)
            for value in selected_year
        ]

        if "year" in result.columns:
            result = result[
                result["year"].astype(str).isin(year_values)
            ]
        elif "month" in result.columns:
            result = result[
                result["month"].astype(str).str[:4].isin(year_values)
            ]

    if (
        selected_status
        and "All" not in selected_status
        and "order_status" in result.columns
    ):
        result = result[
            result["order_status"].astype(str).isin(selected_status)
        ]

    if (
        selected_payment
        and "All" not in selected_payment
        and "payment_mode" in result.columns
    ):
        result = result[
            result["payment_mode"].astype(str).isin(selected_payment)
        ]

    if (
        selected_vehicle
        and "All" not in selected_vehicle
        and "vehicle_type" in result.columns
    ):
        result = result[
            result["vehicle_type"].astype(str).isin(selected_vehicle)
        ]

    if "month" in result.columns:
        months = pd.to_datetime(
            result["month"].astype(str),
            errors="coerce",
        )

        valid = months.notna()

        if valid.any():
            start_period = pd.Timestamp(start_date).to_period("M")
            end_period = pd.Timestamp(end_date).to_period("M")

            result = result[
                (~valid)
                | months.dt.to_period("M").between(
                    start_period,
                    end_period,
                )
            ]

    return result.drop_duplicates()


def prepare_chart_data(df):
    """Prepare a clean, chart-safe DataFrame."""

    if df is None or df.empty:
        return pd.DataFrame()

    result = df.copy()

    # Plotly requires unique column names.
    result = result.loc[:, ~result.columns.duplicated()].copy()

    # Remove completely empty rows and duplicate rows.
    result = result.dropna(how="all")
    result = result.drop_duplicates()

    # Replace infinite numeric values before plotting.
    for column in result.columns:
        if pd.api.types.is_numeric_dtype(result[column]):
            result[column] = result[column].replace(
                [float("inf"), float("-inf")],
                pd.NA,
            )

    return result


def first_categorical(df, preferred=None):
    """Return a usable category/label column."""

    if preferred and preferred in df.columns:
        # IDs can be numeric but are still valid category labels.
        return preferred

    preferred_order = [
        "store_name",
        "store_name_clean",
        "product_name",
        "city",
        "category",
        "brand",
        "role",
        "vehicle_type",
        "payment_mode",
        "platform_name",
        "month",
        "year",
        "distance_band",
        "store_id",
        "product_id",
        "customer_id",
    ]

    for column in preferred_order:
        if column in df.columns:
            return column

    for column in df.columns:
        if not pd.api.types.is_numeric_dtype(df[column]):
            return column

    # A numeric ID can still be used as a category.
    for column in df.columns:
        if str(column).lower().endswith("_id"):
            return column

    return None


def first_numeric(df, preferred=None, exclude=None):
    """Return the best numeric field, including common alias names."""

    exclude = exclude or []

    aliases = {
        "product_count": ["product_count", "products"],
        "customer_count": ["customer_count", "customers"],
        "customer_growth": ["customer_growth", "customers_acquired", "new_customers", "customers"],
        "store_count": ["store_count", "stores", "dark_store_count"],
        "item_value": ["item_value", "item_revenue", "line_total_inr"],
        "inventory_value": ["inventory_value", "excess_inventory_value"],
        "order_value": ["order_value", "total_order_value", "total_revenue"],
        "revenue": ["revenue", "total_revenue", "order_value"],
        "orders": ["orders", "total_orders"],
        "average_order_value": ["average_order_value", "aov"],
        "delay_rate_percent": ["delay_rate_percent", "delay_rate", "delayed_delivery_percent"],
        "average_rating": ["average_rating", "delivery_rating", "average_delivery_rating"],
    }

    if preferred:
        candidates = aliases.get(preferred, [preferred])
        for candidate in candidates:
            if (
                candidate in df.columns
                and candidate not in exclude
                and pd.api.types.is_numeric_dtype(df[candidate])
            ):
                return candidate

    preferred_order = [
        "revenue",
        "total_revenue",
        "orders",
        "total_orders",
        "profit",
        "profit_margin_percent",
        "margin_percent",
        "discount_rate_percent",
        "discount_percent",
        "products",
        "product_count",
        "customers",
        "customer_count",
        "customers_acquired",
        "new_customers",
        "units_sold",
        "item_revenue",
        "item_value",
        "line_total_inr",
        "delay_rate_percent",
        "delayed_delivery_percent",
        "average_rating",
        "average_delivery_rating",
        "selling_price",
        "stock_units",
        "reorder_level",
        "inventory_value",
        "excess_inventory_value",
        "orders_per_sqft",
        "value_per_unit",
        "average_order_value",
        "average_items_per_order",
        "growth_percent",
    ]

    for column in preferred_order:
        if (
            column in df.columns
            and column not in exclude
            and pd.api.types.is_numeric_dtype(df[column])
        ):
            return column

    for column in df.columns:
        if (
            column not in exclude
            and pd.api.types.is_numeric_dtype(df[column])
        ):
            return column

    return None


# ============================================================
# STEP 13: MATPLOTLIB FALLBACK CHARTS
# ============================================================

def matplotlib_bar(df, x, y, title, horizontal=False):
    temp = prepare_chart_data(df)

    if temp.empty:
        st.info("No chart data is available for the selected filters.")
        return

    fig, ax = plt.subplots(figsize=(9, 4.6))

    fig.patch.set_facecolor(theme["dark"])
    ax.set_facecolor(theme["panel"])

    if horizontal:
        ax.barh(
            temp[x].astype(str),
            temp[y],
            color=theme["primary"],
        )
        ax.invert_yaxis()
    else:
        ax.bar(
            temp[x].astype(str),
            temp[y],
            color=theme["primary"],
        )
        ax.tick_params(
            axis="x",
            rotation=35,
        )

    ax.set_title(
        title,
        color="#F6F0F8",
        fontsize=13,
        fontweight="bold",
        pad=11,
    )

    ax.tick_params(
        colors="#CEC4D5"
    )

    ax.grid(
        axis="y",
        alpha=.13,
    )

    fig.tight_layout()
    st.pyplot(
        fig,
        use_container_width=True,
    )
    plt.close(fig)


def matplotlib_line(df, x, y, title):
    temp = prepare_chart_data(df)

    if temp.empty:
        st.info("No chart data is available for the selected filters.")
        return

    fig, ax = plt.subplots(figsize=(9, 4.6))

    fig.patch.set_facecolor(theme["dark"])
    ax.set_facecolor(theme["panel"])

    ax.plot(
        temp[x].astype(str),
        temp[y],
        marker="o",
        linewidth=2.5,
        color=theme["primary"],
    )

    ax.set_title(
        title,
        color="#F6F0F8",
        fontsize=13,
        fontweight="bold",
        pad=11,
    )

    ax.tick_params(
        colors="#CEC4D5"
    )

    ax.grid(alpha=.13)

    fig.tight_layout()
    st.pyplot(
        fig,
        use_container_width=True,
    )
    plt.close(fig)


# ============================================================
# STEP 14: PLOTLY CHART HELPERS
# ============================================================

def chart_layout(fig, title, height=410):
    fig.update_layout(
        title={
            "text": title,
            "x": .5,
            "xanchor": "center",
            "font": {
                "size": 16,
                "color": "#F6F0F8",
            },
        },
        paper_bgcolor=theme["dark"],
        plot_bgcolor=theme["panel"],
        font={
            "color": "#D9D1DE",
        },
        margin={
            "l": 70,
            "r": 30,
            "t": 65,
            "b": 55,
        },
        height=height,
    )

    fig.update_xaxes(
        gridcolor="rgba(255,255,255,0.07)",
        zerolinecolor="rgba(255,255,255,0.08)",
    )

    fig.update_yaxes(
        gridcolor="rgba(255,255,255,0.07)",
        zerolinecolor="rgba(255,255,255,0.08)",
    )

    return fig


def draw_bar_chart(
    df,
    preferred_x,
    preferred_y,
    title,
    horizontal=False,
    top_n=10,
):
    """Draw a readable bar chart and safely handle small/one-row results."""

    temp = prepare_chart_data(df)

    if temp.empty:
        st.info("No chart data is available for the selected filters.")
        return

    x = first_categorical(
        temp,
        preferred_x,
    )

    y = first_numeric(
        temp,
        preferred_y,
    )

    if y is None:
        st.info("The query returned data, but no numeric chart field was available.")
        return

    # A one-row numeric result is still useful as a chart.
    if x is None:
        numeric_value = pd.to_numeric(temp[y].iloc[0], errors="coerce")
        if pd.isna(numeric_value):
            st.info("No chart data is available for the selected filters.")
            return

        x = "chart_label"
        temp = pd.DataFrame(
            {
                "chart_label": [
                    title.replace("?", "").strip()
                ],
                y: [numeric_value],
            }
        )

    temp[x] = temp[x].astype(str)
    temp[y] = pd.to_numeric(temp[y], errors="coerce")
    temp = temp.dropna(subset=[y])

    if temp.empty:
        st.info("No chart data is available for the selected filters.")
        return

    temp = temp.sort_values(
        y,
        ascending=not horizontal,
    ).head(top_n)

    # Aggregate repeated labels before plotting.
    if x != "chart_label" and temp[x].duplicated().any():
        temp = (
            temp.groupby(x, as_index=False)[y]
            .sum()
            .sort_values(y, ascending=not horizontal)
            .head(top_n)
        )

    if temp.empty:
        st.info("No chart data is available for the selected filters.")
        return

    if not PLOTLY_AVAILABLE:
        matplotlib_bar(
            temp,
            x,
            y,
            title,
            horizontal=horizontal,
        )
        return

    if horizontal:
        fig = px.bar(
            temp,
            x=y,
            y=x,
            orientation="h",
            color_discrete_sequence=[theme["primary"]],
        )
    else:
        fig = px.bar(
            temp,
            x=x,
            y=y,
            color_discrete_sequence=[theme["primary"]],
        )

    # Bar traces use marker properties, not trace-level line_color.
    fig.update_traces(
        marker_color=theme["primary"],
        marker_line_width=0,
    )

    chart_height = max(400, min(620, 300 + len(temp) * 36))
    chart_layout(
        fig,
        title,
        height=chart_height,
    )

    fig.update_layout(
        bargap=0.20,
        showlegend=False,
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={
            "displayModeBar": True,
        },
    )

def draw_line_chart(
    df,
    preferred_x,
    preferred_y,
    title,
    color_column=None,
):
    """Draw a safe line chart; one-point results fall back to a bar chart."""

    temp = prepare_chart_data(df)

    if temp.empty:
        st.info("No chart data is available for the selected filters.")
        return

    if preferred_x in temp.columns:
        x = preferred_x
    elif "month" in temp.columns:
        x = "month"
    elif "year" in temp.columns:
        x = "year"
    else:
        x = first_categorical(temp)

    y = first_numeric(
        temp,
        preferred_y,
    )

    if x is None or y is None:
        st.info("No chart could be drawn because the query returned no usable plotting fields.")
        return

    temp[x] = temp[x].astype(str)
    temp[y] = pd.to_numeric(temp[y], errors="coerce")
    temp = temp.dropna(subset=[y])

    if temp.empty:
        st.info("No chart data is available for the selected filters.")
        return

    # A line with only one point is not informative. Use a bar instead.
    if len(temp) == 1:
        draw_bar_chart(
            temp,
            x,
            y,
            title,
            horizontal=False,
            top_n=1,
        )
        return

    if not PLOTLY_AVAILABLE:
        matplotlib_line(
            temp,
            x,
            y,
            title,
        )
        return

    columns = [x, y]
    if color_column and color_column in temp.columns and color_column != x:
        columns.append(color_column)
    temp = temp[columns].copy()

    if color_column and color_column in temp.columns and color_column != x:
        fig = px.line(
            temp,
            x=x,
            y=y,
            color=color_column,
            markers=True,
            color_discrete_sequence=[
                theme["primary"],
                theme["secondary"],
                theme["accent"],
            ],
        )
    else:
        fig = px.line(
            temp,
            x=x,
            y=y,
            markers=True,
            color_discrete_sequence=[theme["primary"]],
        )

        fig.update_traces(
            line={
                "color": theme["primary"],
                "width": 3,
            },
            marker={
                "color": theme["primary"],
                "size": 7,
            },
        )

    chart_layout(
        fig,
        title,
        height=430,
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={
            "displayModeBar": True,
        },
    )

def draw_scatter_chart(
    df,
    preferred_x,
    preferred_y,
    title,
):
    """Use scatter only for relationship questions; otherwise choose a clearer chart."""

    temp = prepare_chart_data(df)

    if temp.empty:
        st.info("No chart data is available for the selected filters.")
        return

    title_lower = title.lower()

    # Ranking / growth questions are easier to understand as bars or lines.
    bar_keywords = [
        "store",
        "product",
        "basket",
        "customer growth",
        "employee productivity",
        "staffing",
        "critical",
        "quantity",
        "value",
        "opportunity",
        "underutilized",
        "high customers",
        "strategically",
    ]

    line_keywords = [
        "growth compare",
        "growth translating",
        "growth converting",
        "over time",
    ]

    if any(keyword in title_lower for keyword in line_keywords):
        # Prefer a monthly/year column when available.
        x = "month" if "month" in temp.columns else (
            "year" if "year" in temp.columns else first_categorical(temp)
        )
        y = first_numeric(temp, preferred_y)

        if x is not None and y is not None:
            draw_line_chart(
                temp,
                x,
                y,
                title,
            )
            return

    if any(keyword in title_lower for keyword in bar_keywords):
        label = first_categorical(temp)
        metric = first_numeric(temp, preferred_y)

        if label is not None and metric is not None:
            draw_bar_chart(
                temp,
                label,
                metric,
                title,
                horizontal=True,
                top_n=10,
            )
            return

    # Keep scatter for genuine relationship questions such as distance vs delay.
    x = first_numeric(temp, preferred_x)
    y = first_numeric(temp, preferred_y, exclude=[x])

    if x is None or y is None:
        label = first_categorical(temp)
        metric = first_numeric(temp, preferred_y)
        if label is not None and metric is not None:
            draw_bar_chart(
                temp,
                label,
                metric,
                title,
                horizontal=True,
                top_n=10,
            )
            return

        st.info("The query returned data, but there are not enough chart fields.")
        return

    temp[x] = pd.to_numeric(temp[x], errors="coerce")
    temp[y] = pd.to_numeric(temp[y], errors="coerce")
    temp = temp.dropna(subset=[x, y])

    if temp.empty:
        st.info("No chart data is available for the selected filters.")
        return

    if not PLOTLY_AVAILABLE:
        fig, ax = plt.subplots(figsize=(9, 4.6))
        fig.patch.set_facecolor(theme["dark"])
        ax.set_facecolor(theme["panel"])
        ax.scatter(
            temp[x],
            temp[y],
            color=theme["primary"],
            s=55,
        )
        ax.set_title(
            title,
            color="#F6F0F8",
            fontsize=13,
            fontweight="bold",
        )
        ax.tick_params(colors="#CEC4D5")
        ax.grid(alpha=.13)
        fig.tight_layout()
        st.pyplot(fig, use_container_width=True)
        plt.close(fig)
        return

    fig = px.scatter(
        temp,
        x=x,
        y=y,
        color_discrete_sequence=[theme["primary"]],
    )

    fig.update_traces(
        marker={
            "size": 9,
            "color": theme["primary"],
            "opacity": .85,
        }
    )

    chart_layout(
        fig,
        title,
        height=430,
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={
            "displayModeBar": True,
        },
    )

def draw_pie_chart(
    df,
    preferred_label,
    preferred_value,
    title,
):
    """Draw a donut chart when a real categorical mix exists."""

    temp = prepare_chart_data(df)

    if temp.empty:
        st.info("No chart data is available for the selected filters.")
        return

    label = first_categorical(
        temp,
        preferred_label,
    )

    value = first_numeric(
        temp,
        preferred_value,
    )

    if label is None or value is None:
        st.info("The query returned data, but there is not enough chart data for a pie chart.")
        return

    temp[label] = temp[label].astype(str)
    temp[value] = pd.to_numeric(temp[value], errors="coerce")
    temp = temp.dropna(subset=[value])
    temp = temp[temp[value] >= 0]

    if temp.empty:
        st.info("No chart data is available for the selected filters.")
        return

    temp = temp.groupby(label, as_index=False)[value].sum()
    temp = temp.sort_values(value, ascending=False).head(8)

    if temp.empty:
        st.info("No chart data is available for the selected filters.")
        return

    # A single category cannot meaningfully form a pie, so use a bar.
    if len(temp) == 1:
        draw_bar_chart(
            temp,
            label,
            value,
            title,
            horizontal=True,
            top_n=1,
        )
        return

    if not PLOTLY_AVAILABLE:
        fig, ax = plt.subplots(figsize=(7, 4.7))
        fig.patch.set_facecolor(theme["dark"])
        ax.pie(
            temp[value],
            labels=temp[label].astype(str),
            autopct="%1.1f%%",
        )
        ax.set_title(
            title,
            color="#F6F0F8",
            fontsize=13,
            fontweight="bold",
        )
        fig.tight_layout()
        st.pyplot(fig, use_container_width=True)
        plt.close(fig)
        return

    fig = px.pie(
        temp,
        names=label,
        values=value,
        hole=.48,
        color_discrete_sequence=[
            theme["primary"],
            theme["secondary"],
            theme["accent"],
            "#7C3AED",
            "#F97316",
            "#14B8A6",
            "#3B82F6",
            "#EC4899",
        ],
    )

    fig.update_traces(
        textposition="inside",
        textinfo="percent+label",
        marker={
            "line": {
                "color": theme["dark"],
                "width": 1,
            }
        },
    )

    chart_layout(
        fig,
        title,
        height=430,
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={
            "displayModeBar": True,
        },
    )

def draw_metric_comparison(
    df,
    preferred_label,
    preferred_metrics,
    title,
):
    """Draw a grouped comparison chart with safe fallbacks."""

    temp = prepare_chart_data(df)

    if temp.empty:
        st.info("No chart data is available for the selected filters.")
        return

    label = first_categorical(
        temp,
        preferred_label,
    )

    metrics = [
        column
        for column in preferred_metrics
        if (
            column in temp.columns
            and pd.api.types.is_numeric_dtype(temp[column])
        )
    ]

    if label is None:
        label = first_categorical(temp)

    if not metrics:
        numeric = [
            column
            for column in temp.columns
            if pd.api.types.is_numeric_dtype(temp[column])
        ]
        metrics = numeric[:3]

    if label is None or not metrics:
        st.info("No chart could be drawn because the query returned no usable plotting fields.")
        return

    # Convert labels to strings so numeric IDs work as categories.
    temp[label] = temp[label].astype(str)

    # One metric is better represented as a normal bar chart.
    if len(metrics) == 1:
        draw_bar_chart(
            temp,
            label,
            metrics[0],
            title,
            horizontal=True,
            top_n=10,
        )
        return

    long_df = temp[
        [label] + metrics
    ].melt(
        id_vars=[label],
        value_vars=metrics,
        var_name="metric",
        value_name="value",
    )

    long_df["value"] = pd.to_numeric(
        long_df["value"],
        errors="coerce",
    )
    long_df = long_df.dropna(subset=["value"])

    if long_df.empty:
        st.info("No chart data is available for the selected filters.")
        return

    # Keep the chart readable when there are many categories.
    keep_labels = (
        temp[metrics[0]]
        .abs()
        .sort_values(ascending=False)
        .head(10)
        .index
    )
    short_temp = temp.loc[keep_labels]

    long_df = short_temp[
        [label] + metrics
    ].melt(
        id_vars=[label],
        value_vars=metrics,
        var_name="metric",
        value_name="value",
    )
    long_df["value"] = pd.to_numeric(long_df["value"], errors="coerce")
    long_df = long_df.dropna(subset=["value"])

    if not PLOTLY_AVAILABLE:
        matplotlib_bar(
            long_df,
            label,
            "value",
            title,
            horizontal=False,
        )
        return

    fig = px.bar(
        long_df,
        x=label,
        y="value",
        color="metric",
        barmode="group",
        color_discrete_sequence=[
            theme["primary"],
            theme["secondary"],
            theme["accent"],
        ],
    )

    chart_layout(
        fig,
        title,
        height=max(410, min(560, 300 + len(short_temp) * 30)),
    )

    fig.update_layout(
        bargap=0.20,
        bargroupgap=0.08,
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={
            "displayModeBar": True,
        },
    )

def draw_cost_chart(df, title):
    """Draw a one-row cost breakdown or a monthly cost trend."""

    if df is None or df.empty:
        st.info("No cost data is available for the selected filters.")
        return

    temp = prepare_chart_data(df)

    # Monthly datasets must be plotted by month rather than transposed.
    if "month" in temp.columns and len(temp) > 1:

        if "revenue_per_marketing_rupee" in temp.columns:
            draw_line_chart(
                temp,
                "month",
                "revenue_per_marketing_rupee",
                title,
            )
            return

        cost_columns = [
            column
            for column in [
                "cogs",
                "delivery_cost",
                "marketing_spend",
                "employee_cost",
                "other_opex",
            ]
            if column in temp.columns
        ]

        if len(cost_columns) >= 2:
            draw_metric_comparison(
                temp,
                "month",
                cost_columns,
                title,
            )
            return

    numeric_columns = [
        column
        for column in temp.columns
        if pd.api.types.is_numeric_dtype(temp[column])
    ]

    if not numeric_columns:
        st.info("No numeric cost values are available for this chart.")
        return

    cost_table = pd.DataFrame(
        {
            "cost_category": numeric_columns,
            "value": [
                pd.to_numeric(
                    temp[column].iloc[0],
                    errors="coerce",
                )
                for column in numeric_columns
            ],
        }
    ).dropna(subset=["value"])

    draw_bar_chart(
        cost_table,
        "cost_category",
        "value",
        title,
        horizontal=True,
        top_n=10,
    )


# ============================================================
# STEP 15: KPI CARD HELPERS
# ============================================================
# Monetary KPI values such as Revenue, COGS, Operating Expense,
# Profit and AOV are displayed compactly as ₹K / ₹M / ₹B.
# This keeps large numbers readable inside KPI cards.

def format_number(value):
    if pd.isna(value):
        return "N/A"

    number = float(value)

    if abs(number) >= 1_000_000_000:
        return f"{number / 1_000_000_000:.2f}B"

    if abs(number) >= 1_000_000:
        return f"{number / 1_000_000:.2f}M"

    if abs(number) >= 1_000:
        return f"{number / 1_000:.1f}K"

    if number.is_integer():
        return f"{int(number):,}"

    return f"{number:,.2f}"


def format_kpi_value(df, title):
    if df is None or df.empty:
        return "N/A"

    row = df.iloc[0]
    title_lower = title.lower()

    if "mix" in title_lower:
        text_columns = [
            column
            for column in df.columns
            if not pd.api.types.is_numeric_dtype(df[column])
        ]

        numeric_columns_list = [
            column
            for column in df.columns
            if pd.api.types.is_numeric_dtype(df[column])
        ]

        if text_columns and numeric_columns_list:
            label = str(
                row[text_columns[0]]
            )

            numeric_value = row[
                numeric_columns_list[-1]
            ]

            if (
                "percent" in numeric_columns_list[-1].lower()
                or "share" in numeric_columns_list[-1].lower()
            ):
                return (
                    f"{label}: "
                    f"{float(numeric_value):.1f}%"
                )

            return label

    for column in df.columns:
        value = row[column]

        if pd.isna(value):
            continue

        if pd.api.types.is_numeric_dtype(df[column]):
            column_name = str(column).lower()

            if (
                "percent" in column_name
                or "margin" in column_name
                or "rate" in column_name
            ):
                return f"{float(value):.2f}%"

            monetary_title = any(
                word in title_lower
                for word in [
                    "revenue",
                    "cogs",
                    "operating expense",
                    "expense",
                    "profit",
                    "salary",
                    "cost",
                    "aov",
                    "value",
                ]
            )

            monetary_column = any(
                word in column_name
                for word in [
                    "revenue",
                    "value",
                    "salary",
                    "cost",
                    "expense",
                    "cogs",
                    "profit",
                    "aov",
                ]
            )

            if monetary_title or monetary_column:
                return "₹" + format_number(value)

            if "rating" in column_name:
                return f"{float(value):.2f}"

            return format_number(value)

    return str(row.iloc[0])


def show_kpi_cards(results, titles):
    columns = st.columns(len(results))

    for index in range(len(results)):
        with columns[index]:
            st.metric(
                label=titles[index],
                value=format_kpi_value(
                    results[index],
                    titles[index],
                ),
            )


def show_question(number, question):
    st.markdown(
        f"""
        <div class="question-card">
            {number}. {question}
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_hero():
    st.markdown(
        f"""
        <div class="hero">
            <div class="hero-title">
                {theme["icon"]} {selected_platform} Analytics Command Center
            </div>
            <div class="hero-subtitle">
                Modern executive view of commercial performance, stores,
                workforce, products, customers, orders, inventory,
                logistics and profitability.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_section_header(title, subtitle_text):
    st.markdown(
        f'<div class="section-title">{title}</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        f'<div class="section-subtitle">{subtitle_text}</div>',
        unsafe_allow_html=True,
    )


# ============================================================
# ZEPTO — FULL QUERY-BY-QUERY DASHBOARD
# ============================================================

def render_zepto_overview():

    # ========================================================
    # 1. ZEPTO — OVERVIEW
    # ========================================================

    show_section_header(
        "Zepto — Overview",
        "Executive snapshot of business scale, growth, customer economics, operations and profitability.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: Total Orders
    query = """
    SELECT COUNT(*) AS total_orders
        FROM orders
        WHERE platform_id = ?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: Total Revenue
    query = """
    SELECT ROUND(SUM(order_value_inr), 2) AS total_revenue
        FROM orders
        WHERE platform_id = ?
          AND order_value_inr IS NOT NULL
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: Average Order Value (AOV)
    query = """
    SELECT ROUND(AVG(order_value_inr), 2) AS average_order_value
        FROM orders
        WHERE platform_id = ?
          AND order_value_inr IS NOT NULL
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: Discount Rate
    query = """
    SELECT ROUND(
            SUM(COALESCE(discount_inr, 0)) * 100.0
            / NULLIF(SUM(COALESCE(order_value_inr, 0)), 0),
            2
        ) AS discount_rate_percent
        FROM orders
        WHERE platform_id = ?
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: Profit Margin
    query = """
    SELECT ROUND(
            SUM(profit_inr) * 100.0
            / NULLIF(SUM(revenue_inr), 0),
            2
        ) AS profit_margin_percent
        FROM pnl_monthly_safe
        WHERE platform_id = ?
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Total Orders",
            "Total Revenue",
            "Average Order Value (AOV)",
            "Discount Rate",
            "Profit Margin",
        ],
    )

    # --------------------------------------------------------
    # FOUR BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: How is Zepto performing overall compared with the other platforms?
    show_question(1, "How is Zepto performing overall compared with the other platforms?")

    query = """
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
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "platform_name",
        "total_revenue",
        "How is Zepto performing overall compared with the other platforms?",
        horizontal=True,
    )

    # Question 2: Is Zepto's business growing or declining over time?
    show_question(2, "Is Zepto's business growing or declining over time?")

    query = """
    SELECT
            SUBSTR(order_datetime, 1, 4) AS year,
            COUNT(*) AS orders,
            ROUND(SUM(COALESCE(order_value_inr, 0)), 2) AS revenue
        FROM orders
        WHERE platform_id = ?
        GROUP BY SUBSTR(order_datetime, 1, 4)
        ORDER BY year
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: LINE CHART
    color_column = None

    draw_line_chart(
        question_2_result,
        "year",
        "revenue",
        "Is Zepto's business growing or declining over time?",
        color_column=color_column,
    )

    # Question 3: Which cities contribute the most to Zepto's business?
    show_question(3, "Which cities contribute the most to Zepto's business?")

    query = """
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
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_3_result,
        "city",
        "revenue",
        "Which cities contribute the most to Zepto's business?",
        horizontal=True,
    )

    # Question 4: Is Zepto relying heavily on discounts to generate orders?
    show_question(4, "Is Zepto relying heavily on discounts to generate orders?")

    query = """
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
    """
    question_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_4_result = apply_dashboard_filters(
        question_4_result
    )

    # CHART TYPE: LINE CHART
    color_column = None

    draw_line_chart(
        question_4_result,
        "month",
        "discount_rate_percent",
        "Is Zepto relying heavily on discounts to generate orders?",
        color_column=color_column,
    )

    # Question 5: Is Zepto's profitability improving or declining over time?
    show_question(5, "Is Zepto's profitability improving or declining over time?")

    query = """
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
    """
    question_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_5_result = apply_dashboard_filters(
        question_5_result
    )

    # CHART TYPE: LINE CHART
    color_column = None

    draw_line_chart(
        question_5_result,
        "month",
        "profit_margin_percent",
        "Is Zepto's profitability improving or declining over time?",
        color_column=color_column,
    )


def render_zepto_store():

    # ========================================================
    # 2. ZEPTO — STORE
    # ========================================================

    show_section_header(
        "Zepto — Store",
        "Store network size, productivity, utilization and capacity decisions.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: Number of Dark Stores
    query = """
    SELECT COUNT(*) AS dark_store_count
        FROM dark_stores
        WHERE platform_id = ?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: Orders per Store
    query = """
    SELECT ROUND(
            (SELECT COUNT(*) FROM orders WHERE platform_id = ?) * 1.0
            / NULLIF((SELECT COUNT(*) FROM dark_stores WHERE platform_id = ?), 0),
            2
        ) AS orders_per_store
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id] * 2,
    )

    # KPI 3: Average Store Size (sqft)
    query = """
    SELECT ROUND(AVG(sqft_area), 2) AS average_store_size_sqft
        FROM dark_stores
        WHERE platform_id = ?
          AND sqft_area IS NOT NULL
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: Orders per Sqft
    query = """
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
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id] * 2,
    )

    # KPI 5: Store Revenue Contribution
    query = """
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
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id] * 2,
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Number of Dark Stores",
            "Orders per Store",
            "Average Store Size (sqft)",
            "Orders per Sqft",
            "Store Revenue Contribution",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which Zepto stores generate the highest number of orders?
    show_question(1, "Which Zepto stores generate the highest number of orders?")

    query = """
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
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id] * 2,
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "store_name",
        "orders",
        "Which Zepto stores generate the highest number of orders?",
        horizontal=True,
    )

    # Question 2: Which stores are underutilized?
    show_question(2, "Which stores are underutilized?")

    query = """
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
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id] * 2,
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_2_result,
        "store_name",
        "orders_per_sqft",
        "Which stores are underutilized?",
        horizontal=True,
    )

    # Question 3: Which cities have the highest concentration of Zepto stores?
    show_question(3, "Which cities have the highest concentration of Zepto stores?")

    query = """
    SELECT
            city,
            COUNT(*) AS dark_stores
        FROM dark_stores
        WHERE platform_id = ?
        GROUP BY city
        ORDER BY dark_stores DESC
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_3_result,
        "city",
        "orders_per_store",
        "Which cities have the highest concentration of Zepto stores?",
        horizontal=True,
    )

def render_zepto_employee():

    # ========================================================
    # 3. ZEPTO — EMPLOYEE
    # ========================================================

    show_section_header(
        "Zepto — Employee",
        "Workforce size, staffing balance, salary cost and productivity.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: Total Employees
    query = """
    SELECT COUNT(*) AS total_employees
        FROM employees e
        JOIN dark_stores ds
            ON e.store_id = ds.store_id
        WHERE ds.platform_id = ?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: Currently Working Employees
    query = """
    SELECT COUNT(*) AS currently_working_employees
        FROM employees e
        JOIN dark_stores ds
            ON e.store_id = ds.store_id
        WHERE ds.platform_id = ?
          AND e.work_status = 'Currently Working'
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: Average Monthly Salary
    query = """
    SELECT ROUND(AVG(e.monthly_salary_inr), 2) AS average_monthly_salary
        FROM employees e
        JOIN dark_stores ds
            ON e.store_id = ds.store_id
        WHERE ds.platform_id = ?
          AND e.monthly_salary_inr IS NOT NULL
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: Employees per Store
    query = """
    SELECT ROUND(
            COUNT(e.employee_id) * 1.0
            / NULLIF(COUNT(DISTINCT ds.store_id), 0),
            2
        ) AS employees_per_store
        FROM dark_stores ds
        LEFT JOIN employees e
            ON ds.store_id = e.store_id
        WHERE ds.platform_id = ?
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: Employee Cost per Order
    query = """
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
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id] * 2,
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Total Employees",
            "Currently Working Employees",
            "Average Monthly Salary",
            "Employees per Store",
            "Employee Cost per Order",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which roles have the highest salary cost?
    show_question(1, "Which roles have the highest salary cost?")

    query = """
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
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_3_result,
        "role",
        "total_monthly_cost",
        "Which roles have the highest salary cost?",
        horizontal=True,
    )

    # Question 2: Which cities have the highest workforce cost?
    show_question(2, "Which cities have the highest workforce cost?")

    query = """
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
    """
    question_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_4_result = apply_dashboard_filters(
        question_4_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_4_result,
        "city",
        "monthly_employee_cost",
        "Which cities have the highest workforce cost?",
        horizontal=True,
    )

    # Question 3: How does employee productivity vary across Zepto cities?
    show_question(3, "How does employee productivity vary across Zepto cities?")

    query = """
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
    """
    question_5_result = fetch_data(
        query,
        [selected_platform_id] * 2,
    )

    question_5_result = apply_dashboard_filters(
        question_5_result
    )

    # CHART TYPE: SCATTER CHART
    draw_scatter_chart(
        question_5_result,
        "employees",
        "orders",
        "How does employee productivity vary across Zepto cities?",
    )


def render_zepto_product():

    # ========================================================
    # 4. ZEPTO — PRODUCT
    # ========================================================

    show_section_header(
        "Zepto — Product",
        "Catalogue size, category mix, brands, discounts and pricing decisions.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: Number of Products
    query = """
    SELECT COUNT(DISTINCT oi.product_id) AS number_of_products
        FROM order_items oi
        JOIN orders o
            ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: Average Selling Price
    query = """
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
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: Average Discount %
    query = """
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
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: Product Category Count
    query = """
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
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
        ],
        [
            "Number of Products",
            "Average Selling Price",
            "Average Discount %",
            "Product Category Count",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which product categories are most important for Zepto?
    show_question(1, "Which product categories are most important for Zepto?")

    query = """
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
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "category",
        "product_count",
        "Which product categories are most important for Zepto?",
        horizontal=True,
    )

    # Question 2: Which products contribute the most item revenue?
    show_question(2, "Which products contribute the most item revenue?")

    query = """
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
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_2_result,
        "product_name",
        "discount_percent",
        "Which products contribute the most item revenue?",
        horizontal=True,
    )

    # Question 3: Which categories receive the deepest discounts?
    show_question(3, "Which categories receive the deepest discounts?")

    query = """
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
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_3_result,
        "product_name",
        "selling_price",
        "Which categories receive the deepest discounts?",
        horizontal=True,
    )


def render_zepto_customer():

    # ========================================================
    # 5. ZEPTO — CUSTOMER
    # ========================================================

    show_section_header(
        "Zepto — Customer",
        "Customer base, activation, engagement and repeat customer behaviour.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: Total Customers
    query = """
    SELECT COUNT(DISTINCT customer_id) AS total_customers
        FROM orders
        WHERE platform_id = ?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: Active Customers
    # How many active Zepto customers are there?
    query = """
    SELECT
        COUNT(DISTINCT o.customer_id) AS active_customers

    FROM orders o

    JOIN customers c
        ON o.customer_id = c.customer_id

    WHERE o.platform_id = ?
      AND TRIM(c.signup_platform) = 'Zepto'
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: Customer Activation Rate
    # Active Customers / Total Zepto Customers * 100
    query = """
    WITH platform_customers AS (
        SELECT
            COUNT(DISTINCT customer_id) AS total_customers

        FROM customers

        WHERE TRIM(signup_platform) = 'Zepto'
    ),

    active_customers AS (
        SELECT
            COUNT(DISTINCT o.customer_id) AS active_customers

        FROM orders o

        JOIN customers c
            ON o.customer_id = c.customer_id

        WHERE o.platform_id = ?
          AND TRIM(c.signup_platform) = 'Zepto'
    )

    SELECT
        ROUND(
            active_customers * 100.0 / NULLIF(total_customers, 0),
            2
        ) AS customer_activation_rate

    FROM active_customers
    CROSS JOIN platform_customers
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: Orders per Customer
    # Total Zepto platform orders / Active Zepto Customers
    query = """
    WITH active_customers AS (
        SELECT
            COUNT(DISTINCT o.customer_id) AS active_customers

        FROM orders o

        JOIN customers c
            ON o.customer_id = c.customer_id

        WHERE o.platform_id = ?
          AND TRIM(c.signup_platform) = 'Zepto'
    ),

    platform_orders AS (
        SELECT
            COUNT(DISTINCT order_id) AS total_orders

        FROM orders

        WHERE platform_id = ?
    )

    SELECT
        ROUND(
            total_orders * 1.0 / NULLIF(active_customers, 0),
            2
        ) AS orders_per_customer

    FROM active_customers
    CROSS JOIN platform_orders
    """
    kpi_4_result = fetch_data(
        query,
        [
            selected_platform_id,
            selected_platform_id,
        ],
    )

    # KPI 5: Repeat Customer Rate
    # Customers with more than one order / Active Customers * 100
    query = """
    WITH customer_order_counts AS (
        SELECT
            o.customer_id,
            COUNT(DISTINCT o.order_id) AS order_count

        FROM orders o

        JOIN customers c
            ON o.customer_id = c.customer_id

        WHERE o.platform_id = ?
          AND TRIM(c.signup_platform) = 'Zepto'

        GROUP BY o.customer_id
    )

    SELECT
        ROUND(
            SUM(
                CASE
                    WHEN order_count > 1 THEN 1
                    ELSE 0
                END
            ) * 100.0 / NULLIF(COUNT(*), 0),
            2
        ) AS repeat_customer_rate

    FROM customer_order_counts
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Total Customers",
            "Active Customers",
            "Customer Activation Rate",
            "Orders per Customer",
            "Repeat Customer Rate",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which cities have the largest Zepto customer base?
    show_question(1, "Which cities have the largest Zepto customer base?")

    query = """
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
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "city",
        "customer_count",
        "Which cities have the largest Zepto customer base?",
        horizontal=True,
    )

    # Question 2: Which cities show the strongest customer acquisition?
    show_question(2, "Which cities show the strongest customer acquisition?")

    query = """
    SELECT
            c.city,
            COUNT(DISTINCT c.customer_id) AS customers_acquired
        FROM customers c
        WHERE LOWER(TRIM(c.signup_platform)) = 'zepto'
        GROUP BY c.city
        ORDER BY customers_acquired DESC
    """
    question_2_result = fetch_data(
        query,
        [],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: HORIZONTAL BAR CHART
    draw_bar_chart(
        question_2_result,
        "city",
        "customers_acquired",
        "Which Cities Show the Strongest Customer Acquisition?",
        horizontal=True,
    )


def render_zepto_orders():

    # ========================================================
    # 6. ZEPTO — ORDERS
    # ========================================================

    show_section_header(
        "Zepto — Orders",
        "Order volume, AOV, completion, cancellations, returns and payment behavior.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: Total Orders
    query = """
    SELECT COUNT(*) AS total_orders
        FROM orders
        WHERE platform_id = ?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: Average Order Value
    query = """
    SELECT ROUND(AVG(order_value_inr), 2) AS average_order_value
        FROM orders
        WHERE platform_id = ?
          AND order_value_inr IS NOT NULL
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: Order Completion Rate
    query = """
    SELECT ROUND(
            SUM(CASE WHEN LOWER(order_status) = 'delivered' THEN 1 ELSE 0 END)
            * 100.0 / NULLIF(COUNT(*), 0),
            2
        ) AS order_completion_rate_percent
        FROM orders
        WHERE platform_id = ?
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: Cancellation Rate
    query = """
    SELECT ROUND(
            SUM(CASE WHEN LOWER(order_status) = 'cancelled' THEN 1 ELSE 0 END)
            * 100.0 / NULLIF(COUNT(*), 0),
            2
        ) AS cancellation_rate_percent
        FROM orders
        WHERE platform_id = ?
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: Return Rate
    query = """
    SELECT ROUND(
            SUM(CASE WHEN LOWER(order_status) = 'returned' THEN 1 ELSE 0 END)
            * 100.0 / NULLIF(COUNT(*), 0),
            2
        ) AS return_rate_percent
        FROM orders
        WHERE platform_id = ?
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Total Orders",
            "Average Order Value",
            "Order Completion Rate",
            "Cancellation Rate",
            "Return Rate",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which cities have the highest order volume?
    show_question(1, "Which cities have the highest order volume?")

    query = """
    SELECT
            ds.city,
            COUNT(o.order_id) AS orders
        FROM orders o
        JOIN dark_stores ds
            ON o.store_id = ds.store_id
        WHERE o.platform_id = ?
        GROUP BY ds.city
        ORDER BY orders DESC
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "city",
        "total_orders",
        "Which cities have the highest order volume?",
        horizontal=True,
    )

    # Question 2: Which cities have the highest cancellation rate?
    show_question(2, "Which cities have the highest cancellation rate?")

    query = """
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
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_2_result,
        "city",
        "cancellation_rate_percent",
        "Which cities have the highest cancellation rate?",
        horizontal=True,
    )

    # Question 3: How is Zepto's AOV changing over time?
    show_question(3, "How is Zepto's AOV changing over time?")

    query = """
    SELECT
            SUBSTR(order_datetime, 1, 7) AS month,
            ROUND(AVG(order_value_inr), 2) AS average_order_value,
            COUNT(*) AS orders
        FROM orders
        WHERE platform_id = ?
          AND order_value_inr IS NOT NULL
        GROUP BY SUBSTR(order_datetime, 1, 7)
        ORDER BY month
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: LINE CHART
    color_column = None

    draw_line_chart(
        question_3_result,
        "month",
        "aov",
        "How is Zepto's AOV changing over time?",
        color_column=color_column,
    )

def render_zepto_order_items():

    # ========================================================
    # 7. ZEPTO — ORDER ITEMS
    # ========================================================

    show_section_header(
        "Zepto — Order Items",
        "Product demand, basket composition, item value and basket growth.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: Units Sold
    query = """
    SELECT SUM(COALESCE(oi.quantity, 0)) AS units_sold
        FROM order_items oi
        JOIN orders o
            ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: Gross Item Value
    query = """
    SELECT ROUND(SUM(COALESCE(oi.line_total_inr, 0)), 2) AS gross_item_value
        FROM order_items oi
        JOIN orders o
            ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: Average Item Price
    query = """
    SELECT ROUND(AVG(oi.item_price_inr), 2) AS average_item_price
        FROM order_items oi
        JOIN orders o
            ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
          AND oi.item_price_inr IS NOT NULL
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: Average Quantity per Order
    query = """
    SELECT ROUND(
            SUM(COALESCE(oi.quantity, 0)) * 1.0
            / NULLIF(COUNT(DISTINCT oi.order_id), 0),
            2
        ) AS average_quantity_per_order
        FROM order_items oi
        JOIN orders o
            ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: Category Contribution
    query = """
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
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Units Sold",
            "Gross Item Value",
            "Average Item Price",
            "Average Quantity per Order",
            "Category Contribution",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which categories generate the most units?
    show_question(1, "Which categories generate the most units?")

    query = """
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
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_2_result,
        "product_name",
        "item_value",
        "Which categories generate the most units?",
        horizontal=True,
    )

    # Question 2: Which products contribute the most item revenue?
    show_question(2, "Which products contribute the most item revenue?")

    query = """
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
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: DONUT / PIE CHART
    draw_pie_chart(
        question_3_result,
        "category",
        "item_value",
        "Which products contribute the most item revenue?",
    )

    # Question 3: Which products have high quantity but low value?
    show_question(3, "Which products have high quantity but low value?")

    query = """
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
    """
    question_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_4_result = apply_dashboard_filters(
        question_4_result
    )

    # CHART TYPE: HORIZONTAL BAR CHART
    # A ranked bar chart is easier to read than a scatter for product-level comparison.
    draw_bar_chart(
        question_4_result,
        "product_name",
        "value_per_unit",
        "High-Quantity vs Low-Value Products",
        horizontal=True,
        top_n=10,
    )

def render_zepto_inventory():

    # ========================================================
    # 8. ZEPTO — INVENTORY
    # ========================================================

    show_section_header(
        "Zepto — Inventory",
        "Stock levels, reorder risk, expiry risk, overstock and working capital.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: Total Stock Units
    query = """
    SELECT
        SUM(COALESCE(i.stock_units, 0)) AS total_stock_units
    FROM inventory i
    JOIN dark_stores ds
        ON i.store_id = ds.store_id
    WHERE ds.platform_id = ?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: Low-stock SKU Count
    query = """
    SELECT
        COUNT(*) AS low_stock_sku_count
    FROM inventory i
    JOIN dark_stores ds
        ON i.store_id = ds.store_id
    WHERE ds.platform_id = ?
      AND COALESCE(i.stock_units, 0) <= COALESCE(i.reorder_level, 0)
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: Stock-to-Reorder Ratio
    query = """
    SELECT
        ROUND(
            SUM(COALESCE(i.stock_units, 0)) * 1.0
            / NULLIF(SUM(COALESCE(i.reorder_level, 0)), 0),
            2
        ) AS stock_to_reorder_ratio
    FROM inventory i
    JOIN dark_stores ds
        ON i.store_id = ds.store_id
    WHERE ds.platform_id = ?
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: Expiring Inventory
    query = """
    SELECT
        SUM(COALESCE(i.stock_units, 0)) AS expiring_inventory_units
    FROM inventory i
    JOIN dark_stores ds
        ON i.store_id = ds.store_id
    WHERE ds.platform_id = ?
      AND i.expiry_date IS NOT NULL
      AND DATE(i.expiry_date) <= DATE('now', '+30 day')
      AND COALESCE(i.stock_units, 0) > 0
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: Inventory Value
    query = """
    SELECT
        ROUND(
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
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Total Stock Units",
            "Low-stock SKU Count",
            "Stock-to-Reorder Ratio",
            "Expiring Inventory",
            "Inventory Value",
        ],
    )

    # --------------------------------------------------------
    # THREE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Lowest inventory stores
    show_question(1,
        "Which Zepto stores have the lowest inventory levels?",
    )

    query = """
    SELECT
        ds.store_id,
        COALESCE(ds.store_name_clean, ds.store_name) AS store_name,
        ds.city,
        ROUND(
            SUM(COALESCE(i.stock_units, 0)),
            2
        ) AS stock_units
    FROM inventory i
    JOIN dark_stores ds
        ON i.store_id = ds.store_id
    WHERE ds.platform_id = ?
    GROUP BY
        ds.store_id,
        ds.city
    ORDER BY stock_units ASC
    LIMIT 15
    """

    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result,
    )

    # CHART TYPE: HORIZONTAL BAR CHART
    # Shows the stores with the lowest total stock first.
    draw_bar_chart(
        question_1_result,
        "store_name",
        "stock_units",
        "Which Zepto Stores Have the Lowest Inventory Levels?",
        horizontal=True,
        top_n=8,
    )

    # Question 2: Excessive stock
    show_question(2,
        "Which stores have excessive stock?",
    )

    query = """
    SELECT
        ds.store_id,
        ds.city,
        ROUND(
            SUM(COALESCE(i.stock_units, 0)),
            2
        ) AS stock_units,
        ROUND(
            SUM(COALESCE(i.reorder_level, 0)),
            2
        ) AS reorder_level,
        ROUND(
            SUM(COALESCE(i.stock_units, 0)) * 1.0
            / NULLIF(
                SUM(COALESCE(i.reorder_level, 0)),
                0
            ),
            2
        ) AS stock_to_reorder_ratio
    FROM inventory i
    JOIN dark_stores ds
        ON i.store_id = ds.store_id
    WHERE ds.platform_id = ?
    GROUP BY
        ds.store_id,
        ds.city
    HAVING stock_to_reorder_ratio > 2
    ORDER BY stock_to_reorder_ratio DESC
    LIMIT 15
    """

    question_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result,
    )

    # CHART TYPE: GROUPED HORIZONTAL BAR CHART
    # Directly compares available stock against reorder requirement.
    draw_metric_comparison(
        question_2_result,
        "store_id",
        [
            "stock_units",
            "reorder_level",
        ],
        "Stores With Excessive Stock — Stock vs Reorder Level",
    )

    # Question 3: Expiry risk
    show_question(3,
        "Which products are at risk of expiry?",
    )

    query = """
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
      AND DATE(i.expiry_date)
          <= DATE('now', '+30 day')
      AND COALESCE(i.stock_units, 0) > 0
    ORDER BY
        DATE(i.expiry_date) ASC,
        stock_units DESC
    LIMIT 20
    """

    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result,
    )

    # CHART TYPE: HORIZONTAL BAR CHART
    draw_bar_chart(
        question_3_result,
        "product_name",
        "stock_units",
        "Products at Risk of Expiry — Stock Units",
        horizontal=True,
        top_n=10,
    )

def render_zepto_logistics():

    # ========================================================
    # 9. ZEPTO — LOGISTICS
    # ========================================================

    show_section_header(
        "Zepto — Logistics",
        "Delays, distance, ratings, vehicle performance and delivery optimization.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: Average Delivery Distance
    query = """
    SELECT ROUND(AVG(l.distance_km), 2) AS average_delivery_distance_km
        FROM logistics l
        JOIN orders o
            ON l.order_id = o.order_id
        WHERE o.platform_id = ?
          AND l.distance_km IS NOT NULL
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: Average Delivery Rating
    query = """
    SELECT ROUND(AVG(l.delivery_rating), 2) AS average_delivery_rating
        FROM logistics l
        JOIN orders o
            ON l.order_id = o.order_id
        WHERE o.platform_id = ?
          AND l.delivery_rating IS NOT NULL
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: Delay Rate
    query = """
    SELECT ROUND(
            SUM(CASE WHEN LOWER(l.delay_flag) IN ('yes', 'y') THEN 1 ELSE 0 END)
            * 100.0 / NULLIF(COUNT(*), 0),
            2
        ) AS delay_rate_percent
        FROM logistics l
        JOIN orders o
            ON l.order_id = o.order_id
        WHERE o.platform_id = ?
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: On-Time Delivery Rate
    query = """
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
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: Delayed Deliveries
    query = """
    SELECT COUNT(*) AS delayed_deliveries
        FROM logistics l
        JOIN orders o
            ON l.order_id = o.order_id
        WHERE o.platform_id = ?
          AND LOWER(l.delay_flag) IN ('yes', 'y')
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Average Delivery Distance",
            "Average Delivery Rating",
            "Delay Rate",
            "On-Time Delivery Rate",
            "Delayed Deliveries",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which cities experience the highest delay rate?
    show_question(1, "Which cities experience the highest delay rate?")

    query = """
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
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "vehicle_type",
        "delay_rate_percent",
        "Which cities experience the highest delay rate?",
        horizontal=True,
    )

    # Question 2: Which vehicle types perform best?
    show_question(2, "Which vehicle types perform best?")

    query = """
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
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_2_result,
        "distance_band",
        "delay_rate_percent",
        "Which vehicle types perform best?",
        horizontal=False,
    )

    # Question 3: Does longer delivery distance increase delays?
    show_question(3, "Does longer delivery distance increase delays?")

    query = """
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
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_3_result,
        "city",
        "average_rating",
        "Does longer delivery distance increase delays?",
        horizontal=True,
    )

def render_zepto_monthly_p_l():

    # ========================================================
    # 10. ZEPTO — MONTHLY P&L
    # ========================================================

    show_section_header(
        "Zepto — Monthly P&L",
        "Revenue, COGS, operating costs, profit and monthly margin trends.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: Revenue
    query = """
    SELECT ROUND(SUM(revenue_inr), 2) AS revenue
        FROM pnl_monthly_safe
        WHERE platform_id = ?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: COGS
    query = """
    SELECT ROUND(SUM(cogs_inr), 2) AS cogs
        FROM pnl_monthly_safe
        WHERE platform_id = ?
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: Operating Cost
    query = """
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
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: Profit
    query = """
    SELECT ROUND(SUM(profit_inr), 2) AS profit
        FROM pnl_monthly_safe
        WHERE platform_id = ?
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: Profit Margin
    query = """
    SELECT ROUND(
            SUM(profit_inr) * 100.0
            / NULLIF(SUM(revenue_inr), 0),
            2
        ) AS profit_margin_percent
        FROM pnl_monthly_safe
        WHERE platform_id = ?
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Revenue",
            "COGS",
            "Operating Cost",
            "Profit",
            "Profit Margin",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which cities generate the highest revenue?
    show_question(1, "Which cities generate the highest revenue?")

    query = """
    SELECT
            city,
            ROUND(SUM(revenue_inr), 2) AS revenue
        FROM pnl_monthly_safe
        WHERE platform_id = ?
        GROUP BY city
        ORDER BY revenue DESC
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_2_result,
        "city",
        "profit_margin_percent",
        "Which cities generate the highest revenue?",
        horizontal=True,
    )

    # Question 2: Which cities generate revenue but remain unprofitable?
    show_question(2, "Which cities generate revenue but remain unprofitable?")

    query = """
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
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_3_result,
        "city",
        "profit",
        "Which cities generate revenue but remain unprofitable?",
        horizontal=True,
    )

    # Question 3: How is Zepto's profit changing month by month?
    show_question(3, "How is Zepto's profit changing month by month?")

    query = """
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
    """
    question_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_5_result = apply_dashboard_filters(
        question_5_result
    )

    # CHART TYPE: LINE CHART
    color_column = None

    draw_line_chart(
        question_5_result,
        "month",
        "profit",
        "How is Zepto's profit changing month by month?",
        color_column=color_column,
    )


# ============================================================
# BLINKIT — FULL QUERY-BY-QUERY DASHBOARD
# ============================================================

def render_blinkit_overview():

    # ========================================================
    # 1. BLINKIT — OVERVIEW
    # ========================================================

    show_section_header(
        "Blinkit — Overview",
        "Executive snapshot of business scale, growth, customer economics, operations and profitability.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: What is Blinkit's total number of orders?
    query = """
    SELECT COUNT(*) AS total_orders
        FROM orders
        WHERE platform_id = ?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: What is Blinkit's total revenue?
    query = """
    SELECT ROUND(COALESCE(SUM(order_value_inr), 0), 2) AS total_revenue
        FROM orders
        WHERE platform_id = ?
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: What is Blinkit's average order value?
    query = """
    SELECT ROUND(COALESCE(AVG(order_value_inr), 0), 2) AS average_order_value
        FROM orders
        WHERE platform_id = ?
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: What is Blinkit's discount rate?
    query = """
    SELECT
            ROUND(
                COALESCE(SUM(discount_inr), 0) * 100.0 /
                NULLIF(COALESCE(SUM(order_value_inr), 0) + COALESCE(SUM(discount_inr), 0), 0),
                2
            ) AS discount_rate_percent
        FROM orders
        WHERE platform_id = ?
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: What is Blinkit's profit margin?
    query = """
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
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Total Orders",
            "Total Revenue",
            "AOV",
            "Discount Rate",
            "Profit Margin",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Is Blinkit gaining or losing business over time?
    show_question(1, "Is Blinkit gaining or losing business over time?")

    query = """
    SELECT
            SUBSTR(order_datetime, 1, 7) AS month,
            COUNT(*) AS orders,
            ROUND(COALESCE(SUM(order_value_inr), 0), 2) AS revenue
        FROM orders
        WHERE platform_id = ?
        GROUP BY SUBSTR(order_datetime, 1, 7)
        ORDER BY month
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "platform_name",
        "total_revenue",
        "Is Blinkit gaining or losing business over time?",
        horizontal=True,
    )

    # Question 2: Which cities are Blinkit's strongest markets?
    show_question(2, "Which cities are Blinkit's strongest markets?")

    query = """
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
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: LINE CHART
    color_column = None

    draw_line_chart(
        question_2_result,
        "year",
        "revenue",
        "Which cities are Blinkit's strongest markets?",
        color_column=color_column,
    )

    # Question 3: Is discounting driving Blinkit's order growth?
    show_question(3, "Is discounting driving Blinkit's order growth?")

    query = """
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
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_3_result,
        "city",
        "revenue",
        "Is discounting driving Blinkit's order growth?",
        horizontal=True,
    )

def render_blinkit_store():

    # ========================================================
    # 2. BLINKIT — STORE
    # ========================================================

    show_section_header(
        "Blinkit — Store",
        "Store network size, productivity, utilization and capacity decisions.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: What is Blinkit's store count?
    query = """
    SELECT COUNT(*) AS store_count
        FROM dark_stores
        WHERE platform_id = ?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: What are Blinkit's orders per store?
    query = """
    SELECT ROUND(
            COUNT(o.order_id) * 1.0 / NULLIF(COUNT(DISTINCT ds.store_id), 0),
            2
        ) AS orders_per_store
        FROM dark_stores ds
        LEFT JOIN orders o
            ON ds.store_id = o.store_id
            AND o.platform_id = ?
        WHERE ds.platform_id = ?
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id] * 2,
    )

    # KPI 3: What is Blinkit's average store size?
    query = """
    SELECT ROUND(COALESCE(AVG(sqft_area), 0), 2) AS average_store_size_sqft
        FROM dark_stores
        WHERE platform_id = ?
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: What is Blinkit's store productivity?
    query = """
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
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id] * 2,
    )

    # KPI 5: What is Blinkit's store revenue contribution?
    query = """
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
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Store Count",
            "Orders per Store",
            "Average Store Size",
            "Store Productivity",
            "Store Revenue Contribution",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which Blinkit dark stores are the top performers?
    show_question(1, "Which Blinkit dark stores are the top performers?")

    query = """
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
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id] * 2,
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "store_name",
        "orders",
        "Which Blinkit dark stores are the top performers?",
        horizontal=True,
    )

    # Question 2: Which Blinkit stores have low utilization?
    show_question(2, "Which Blinkit stores have low utilization?")

    query = """
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
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id] * 2,
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_2_result,
        "store_name",
        "orders_per_sqft",
        "Which Blinkit stores have low utilization?",
        horizontal=True,
    )

    # Question 3: Which cities require additional Blinkit stores?
    show_question(3, "Which cities require additional Blinkit stores?")

    query = """
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
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id] * 2,
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_3_result,
        "city",
        "orders_per_store",
        "Which cities require additional Blinkit stores?",
        horizontal=True,
    )

def render_blinkit_employee():

    # ========================================================
    # 3. BLINKIT — EMPLOYEE
    # ========================================================

    show_section_header(
        "Blinkit — Employee",
        "Workforce size, staffing balance, salary cost and productivity.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: What is Blinkit's total employee count?
    query = """
    SELECT COUNT(*) AS employee_count
        FROM employees e
        JOIN dark_stores ds ON e.store_id = ds.store_id
        WHERE ds.platform_id = ?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: What is Blinkit's active workforce?
    query = """
    SELECT COUNT(*) AS active_workforce
        FROM employees e
        JOIN dark_stores ds ON e.store_id = ds.store_id
        WHERE ds.platform_id = ?
          AND LOWER(TRIM(e.employment_status)) = 'active'
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: What is Blinkit's average monthly salary?
    query = """
    SELECT ROUND(COALESCE(AVG(e.monthly_salary_inr), 0), 2) AS average_monthly_salary
        FROM employees e
        JOIN dark_stores ds ON e.store_id = ds.store_id
        WHERE ds.platform_id = ?
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: What are Blinkit's employees per store?
    query = """
    SELECT ROUND(
            COUNT(e.employee_id) * 1.0 /
            NULLIF(COUNT(DISTINCT ds.store_id), 0),
            2
        ) AS employees_per_store
        FROM dark_stores ds
        LEFT JOIN employees e ON ds.store_id = e.store_id
        WHERE ds.platform_id = ?
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: What is Blinkit's employee cost per order?
    query = """
    SELECT ROUND(
            COALESCE(SUM(employee_cost_inr), 0) /
            NULLIF(COALESCE(SUM(orders_count), 0), 0),
            2
        ) AS employee_cost_per_order
        FROM pnl_monthly
        WHERE platform_id = ?
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Total Employees",
            "Active Employees",
            "Average Monthly Salary",
            "Employees per Store",
            "Employee Cost per Order",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which Blinkit stores are understaffed?
    show_question(1, "Which Blinkit stores are understaffed?")

    query = """
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
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id] * 2,
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "store_name",
        "employee_count",
        "Which Blinkit stores are understaffed?",
        horizontal=True,
    )

    # Question 2: Which Blinkit stores are overstaffed relative to orders?
    show_question(2, "Which Blinkit stores are overstaffed relative to orders?")

    query = """
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
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id] * 2,
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_2_result,
        "store_name",
        "orders_per_employee",
        "Which Blinkit stores are overstaffed relative to orders?",
        horizontal=True,
    )

    # Question 3: Which roles consume the most employee cost?
    show_question(3, "Which roles consume the most employee cost?")

    query = """
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
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_3_result,
        "role",
        "total_monthly_cost",
        "Which roles consume the most employee cost?",
        horizontal=True,
    )

def render_blinkit_product():

    # ========================================================
    # 4. BLINKIT — PRODUCT
    # ========================================================

    show_section_header(
        "Blinkit — Product",
        "Catalogue size, category mix, brands, discounts and pricing decisions.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: What is Blinkit's product count?
    query = """
    SELECT COUNT(DISTINCT oi.product_id) AS product_count
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: What is Blinkit's average selling price?
    query = """
    SELECT ROUND(COALESCE(AVG(p.selling_price), 0), 2) AS average_selling_price
        FROM products p
        WHERE p.product_id IN (
            SELECT DISTINCT oi.product_id
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.order_id
            WHERE o.platform_id = ?
        )
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: What is Blinkit's average product discount?
    query = """
    SELECT ROUND(COALESCE(AVG(p.discount_percent), 0), 2) AS average_discount_percent
        FROM products p
        WHERE p.product_id IN (
            SELECT DISTINCT oi.product_id
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.order_id
            WHERE o.platform_id = ?
        )
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: How many product categories does Blinkit have?
    query = """
    SELECT COUNT(DISTINCT p.category) AS category_count
        FROM products p
        WHERE p.product_id IN (
            SELECT DISTINCT oi.product_id
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.order_id
            WHERE o.platform_id = ?
        )
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: How many Blinkit products are price outliers?
    query = """
    SELECT COUNT(*) AS outlier_products
        FROM products p
        WHERE LOWER(TRIM(p.price_status)) = 'outlier'
          AND p.product_id IN (
              SELECT DISTINCT oi.product_id
              FROM order_items oi
              JOIN orders o ON oi.order_id = o.order_id
              WHERE o.platform_id = ?
          )
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Product Count",
            "Average Selling Price",
            "Average Discount %",
            "Category Count",
            "Price Outlier Count",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which product categories are most important to Blinkit?
    show_question(1, "Which product categories are most important to Blinkit?")

    query = """
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
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "category",
        "product_count",
        "Which product categories are most important to Blinkit?",
        horizontal=True,
    )

    # Question 2: Which product categories receive the highest discounts?
    show_question(2, "Which product categories receive the highest discounts?")

    query = """
    SELECT
            category,
            ROUND(COALESCE(AVG(discount_percent), 0), 2) AS average_discount_percent,
            COUNT(*) AS product_count
        FROM products
        GROUP BY category
        ORDER BY average_discount_percent DESC
    """
    question_2_result = fetch_data(
        query,
        [],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_2_result,
        "product_name",
        "discount_percent",
        "Which product categories receive the highest discounts?",
        horizontal=True,
    )

    # Question 3: Which brands dominate Blinkit's assortment?
    show_question(3, "Which brands dominate Blinkit's assortment?")

    query = """
    SELECT
            COALESCE(brand, 'Unknown') AS brand,
            COUNT(*) AS product_count,
            ROUND(COALESCE(AVG(selling_price), 0), 2) AS average_selling_price
        FROM products
        GROUP BY COALESCE(brand, 'Unknown')
        ORDER BY product_count DESC, average_selling_price DESC
        LIMIT 15
    """
    question_3_result = fetch_data(
        query,
        [],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_3_result,
        "product_name",
        "selling_price",
        "Which brands dominate Blinkit's assortment?",
        horizontal=True,
    )

def render_blinkit_customer():

    # ========================================================
    # 5. BLINKIT — CUSTOMER
    # ========================================================

    show_section_header(
        "Blinkit — Customer",
        "Customer base, acquisition, geography, signup and app mix.",
    )

    # --------------------------------------------------------
    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: Total Customers
    query = """
    SELECT
        COUNT(DISTINCT c.customer_id) AS total_customers
    FROM customers c
    WHERE LOWER(TRIM(c.signup_platform)) = 'blinkit'
    """
    kpi_1_result = fetch_data(
        query,
        [],
    )

    # KPI 2: Active Customers
    # Customers from the platform signup base who have
    # placed at least one order on the selected platform.
    query = """
    SELECT
        COUNT(DISTINCT o.customer_id) AS active_customers
    FROM orders o
    INNER JOIN customers c
        ON o.customer_id = c.customer_id
    WHERE o.platform_id = ?
      AND LOWER(TRIM(c.signup_platform)) = 'blinkit'
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: Customer Activation Rate
    # Active Customers / Total Customers * 100
    query = """
    WITH platform_customers AS (
        SELECT DISTINCT
            c.customer_id
        FROM customers c
        WHERE LOWER(TRIM(c.signup_platform)) = 'blinkit'
    ),
    active_customers AS (
        SELECT DISTINCT
            o.customer_id
        FROM orders o
        INNER JOIN platform_customers pc
            ON o.customer_id = pc.customer_id
        WHERE o.platform_id = ?
    )
    SELECT
        ROUND(
            COUNT(DISTINCT ac.customer_id) * 100.0
            / NULLIF(
                COUNT(DISTINCT pc.customer_id),
                0
            ),
            2
        ) AS activation_rate_percent
    FROM platform_customers pc
    LEFT JOIN active_customers ac
        ON pc.customer_id = ac.customer_id
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: Orders per Customer
    # Total platform orders / Active Customers
    query = """
    WITH platform_customers AS (
        SELECT DISTINCT
            c.customer_id
        FROM customers c
        WHERE LOWER(TRIM(c.signup_platform)) = 'blinkit'
    ),
    active_customers AS (
        SELECT DISTINCT
            o.customer_id
        FROM orders o
        INNER JOIN platform_customers pc
            ON o.customer_id = pc.customer_id
        WHERE o.platform_id = ?
    ),
    platform_orders AS (
        SELECT
            COUNT(DISTINCT o.order_id) AS total_orders
        FROM orders o
        INNER JOIN platform_customers pc
            ON o.customer_id = pc.customer_id
        WHERE o.platform_id = ?
    )
    SELECT
        ROUND(
            po.total_orders * 1.0
            / NULLIF(
                COUNT(DISTINCT ac.customer_id),
                0
            ),
            2
        ) AS orders_per_customer
    FROM active_customers ac
    CROSS JOIN platform_orders po
    """
    kpi_4_result = fetch_data(
        query,
        [
            selected_platform_id,
            selected_platform_id,
        ],
    )

    # KPI 5: Repeat Customer Rate
    # Customers with more than one order / Active Customers * 100
    query = """
    WITH platform_customers AS (
        SELECT DISTINCT
            c.customer_id
        FROM customers c
        WHERE LOWER(TRIM(c.signup_platform)) = 'blinkit'
    ),
    customer_order_counts AS (
        SELECT
            o.customer_id,
            COUNT(DISTINCT o.order_id) AS order_count
        FROM orders o
        INNER JOIN platform_customers pc
            ON o.customer_id = pc.customer_id
        WHERE o.platform_id = ?
        GROUP BY o.customer_id
    )
    SELECT
        ROUND(
            SUM(
                CASE
                    WHEN order_count > 1
                    THEN 1
                    ELSE 0
                END
            ) * 100.0
            / NULLIF(
                COUNT(customer_id),
                0
            ),
            2
        ) AS repeat_customer_rate_percent
    FROM customer_order_counts
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Total Customers",
            "Active Customers",
            "Customer Activation Rate",
            "Orders per Customer",
            "Repeat Customer Rate",
        ],
    )

    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which cities have the strongest Blinkit customer base?
    show_question(1, "Which cities have the strongest Blinkit customer base?")

    query = """
    SELECT
            city,
            COUNT(DISTINCT customer_id) AS customers
        FROM customers
        WHERE LOWER(TRIM(signup_platform)) = 'blinkit'
        GROUP BY city
        ORDER BY customers DESC
    """
    question_1_result = fetch_data(
        query,
        [],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "city",
        "customer_count",
        "Which cities have the strongest Blinkit customer base?",
        horizontal=True,
    )

    # Question 2: Where is Blinkit's customer acquisition weak?
    show_question(2, "Where is Blinkit's customer acquisition weak?")

    query = """
    SELECT
            city,
            COUNT(DISTINCT customer_id) AS new_customers
        FROM customers
        WHERE LOWER(TRIM(signup_platform)) = 'blinkit'
        GROUP BY city
        ORDER BY new_customers ASC
    """
    question_2_result = fetch_data(
        query,
        [],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: HORIZONTAL BAR CHART
    draw_bar_chart(
        question_2_result,
        "city",
        "new_customers",
        "Where is Blinkit's Customer Acquisition Weak?",
        horizontal=True,
    )

    # Question 3: Which signup platforms perform best?
    show_question(3, "Which signup platforms perform best?")

    query = """
    SELECT
            signup_platform,
            COUNT(DISTINCT customer_id) AS customers
        FROM customers
        GROUP BY signup_platform
        ORDER BY customers DESC
    """
    question_3_result = fetch_data(
        query,
        [],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_3_result,
        "signup_platform",
        "customers",
        "Which Signup Platforms Perform Best?",
        horizontal=True,
    )

def render_blinkit_orders():

    # ========================================================
    # 6. BLINKIT — ORDERS
    # ========================================================

    show_section_header(
        "Blinkit — Orders",
        "Order volume, AOV, completion, cancellations, returns and payment behavior.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: What is Blinkit's total order count?
    query = """
    SELECT COUNT(*) AS orders
        FROM orders
        WHERE platform_id = ?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: What is Blinkit's average order value?
    query = """
    SELECT ROUND(COALESCE(AVG(order_value_inr), 0), 2) AS aov
        FROM orders
        WHERE platform_id = ?
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: What is Blinkit's delivered rate?
    query = """
    SELECT ROUND(
            SUM(CASE WHEN order_status = 'Delivered' THEN 1 ELSE 0 END) * 100.0 /
            NULLIF(COUNT(*), 0),
            2
        ) AS delivered_rate_percent
        FROM orders
        WHERE platform_id = ?
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: What is Blinkit's cancellation rate?
    query = """
    SELECT ROUND(
            SUM(CASE WHEN order_status = 'Cancelled' THEN 1 ELSE 0 END) * 100.0 /
            NULLIF(COUNT(*), 0),
            2
        ) AS cancellation_rate_percent
        FROM orders
        WHERE platform_id = ?
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: What is Blinkit's return rate?
    query = """
    SELECT ROUND(
            SUM(CASE WHEN order_status = 'Returned' THEN 1 ELSE 0 END) * 100.0 /
            NULLIF(COUNT(*), 0),
            2
        ) AS return_rate_percent
        FROM orders
        WHERE platform_id = ?
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Total Orders",
            "AOV",
            "Delivered Rate",
            "Cancellation Rate",
            "Return Rate",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Where does Blinkit have the highest order volume?
    show_question(1, "Where does Blinkit have the highest order volume?")

    query = """
    SELECT
            ds.city,
            COUNT(o.order_id) AS orders,
            ROUND(COALESCE(SUM(o.order_value_inr), 0), 2) AS revenue
        FROM orders o
        JOIN dark_stores ds ON o.store_id = ds.store_id
        WHERE o.platform_id = ?
        GROUP BY ds.city
        ORDER BY orders DESC
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "city",
        "total_orders",
        "Where does Blinkit have the highest order volume?",
        horizontal=True,
    )

    # Question 2: Which stores have the highest cancellation rate?
    show_question(2, "Which stores have the highest cancellation rate?")

    query = """
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
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id] * 2,
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_2_result,
        "city",
        "cancellation_rate_percent",
        "Which stores have the highest cancellation rate?",
        horizontal=True,
    )

    # Question 3: Which cities have the most returned orders?
    show_question(3, "Which cities have the most returned orders?")

    query = """
    SELECT
            ds.city,
            COUNT(*) AS returned_orders
        FROM orders o
        JOIN dark_stores ds ON o.store_id = ds.store_id
        WHERE o.platform_id = ?
          AND o.order_status = 'Returned'
        GROUP BY ds.city
        ORDER BY returned_orders DESC
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_3_result,
        "store_name",
        "total_orders",
        "Which cities have the most returned orders?",
        horizontal=True,
    )

def render_blinkit_order_items():

    # ========================================================
    # 7. BLINKIT — ORDER ITEMS
    # ========================================================

    show_section_header(
        "Blinkit — Order Items",
        "Product demand, basket composition, item value and basket growth.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: What are Blinkit's total units sold?
    query = """
    SELECT SUM(COALESCE(oi.quantity, 0)) AS units_sold
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: What is Blinkit's gross item revenue?
    query = """
    SELECT ROUND(COALESCE(SUM(oi.line_total_inr), 0), 2) AS gross_item_revenue
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: What is Blinkit's average item price?
    query = """
    SELECT ROUND(COALESCE(AVG(oi.item_price_inr), 0), 2) AS average_item_price
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: What is Blinkit's average quantity per order?
    query = """
    SELECT ROUND(
            COALESCE(SUM(oi.quantity), 0) * 1.0 /
            NULLIF(COUNT(DISTINCT oi.order_id), 0),
            2
        ) AS average_quantity_per_order
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: What is Blinkit's category contribution?
    query = """
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
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Units Sold",
            "Gross Item Revenue",
            "Average Item Price",
            "Average Quantity per Order",
            "Category Contribution",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: What products are most frequently purchased?
    show_question(1, "What products are most frequently purchased?")

    query = """
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
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "product_name",
        "units_sold",
        "What products are most frequently purchased?",
        horizontal=True,
    )

    # Question 2: Which categories generate the most units?
    show_question(2, "Which categories generate the most units?")

    query = """
    SELECT
            p.category,
            SUM(COALESCE(oi.quantity, 0)) AS units_sold
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.order_id
        JOIN products p ON oi.product_id = p.product_id
        WHERE o.platform_id = ?
        GROUP BY p.category
        ORDER BY units_sold DESC
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_2_result,
        "product_name",
        "item_value",
        "Which categories generate the most units?",
        horizontal=True,
    )

    # Question 3: Which products generate the most item revenue?
    show_question(3, "Which products generate the most item revenue?")

    query = """
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
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: DONUT / PIE CHART
    draw_pie_chart(
        question_3_result,
        "category",
        "item_value",
        "Which products generate the most item revenue?",
    )

def render_blinkit_inventory():

    # ========================================================
    # 8. BLINKIT — INVENTORY
    # ========================================================

    show_section_header(
        "Blinkit — Inventory",
        "Stock levels, reorder risk, expiry risk, overstock and working capital.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: What are Blinkit's total stock units?
    query = """
    SELECT SUM(COALESCE(i.stock_units, 0)) AS stock_units
        FROM inventory i
        JOIN dark_stores ds ON i.store_id = ds.store_id
        WHERE ds.platform_id = ?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: How many Blinkit inventory records are low-stock?
    query = """
    SELECT COUNT(*) AS low_stock_products
        FROM inventory i
        JOIN dark_stores ds ON i.store_id = ds.store_id
        WHERE ds.platform_id = ?
          AND COALESCE(i.stock_units, 0) <= COALESCE(i.reorder_level, 0)
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: What is Blinkit's reorder risk?
    query = """
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
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: What is Blinkit's expiry risk?
    query = """
    SELECT COUNT(*) AS expiry_risk_records
        FROM inventory i
        JOIN dark_stores ds ON i.store_id = ds.store_id
        WHERE ds.platform_id = ?
          AND i.expiry_date IS NOT NULL
          AND julianday(i.expiry_date) - julianday(i.last_restock_date) <= 30
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: What is Blinkit's inventory per store?
    query = """
    SELECT ROUND(
            COALESCE(SUM(i.stock_units), 0) * 1.0 /
            NULLIF(COUNT(DISTINCT ds.store_id), 0),
            2
        ) AS inventory_per_store
        FROM inventory i
        JOIN dark_stores ds ON i.store_id = ds.store_id
        WHERE ds.platform_id = ?
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Total Stock Units",
            "Low-stock SKU Count",
            "Reorder Risk",
            "Expiry Risk",
            "Inventory per Store",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which Blinkit stores face stock shortages?
    show_question(1, "Which Blinkit stores face stock shortages?")

    query = """
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
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "store_name",
        "low_stock_skus",
        "Which Blinkit stores face stock shortages?",
        horizontal=True,
    top_n=8,
)

    # Question 2: Which products are below reorder levels?
    show_question(2, "Which products are below reorder levels?")

    query = """
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
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: GROUPED BAR CHART
    draw_metric_comparison(
        question_2_result,
        "product_name",
        ["stock_units", "reorder_level"],
        "Which products are below reorder levels?",
    )

    # Question 3: Which products are overstocked?
    show_question(3, "Which products are overstocked?")

    query = """
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
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_metric_comparison(
        question_3_result,
        "product_name",
        ["total_stock", "average_reorder_level"],
        "Total Stock vs Reorder Level — Overstocked Products",
    )

def render_blinkit_logistics():

    # ========================================================
    # 9. BLINKIT — LOGISTICS
    # ========================================================

    show_section_header(
        "Blinkit — Logistics",
        "Delays, distance, ratings, vehicle performance and delivery optimization.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: What is Blinkit's delay rate?
    query = """
    SELECT ROUND(
            SUM(CASE WHEN l.delay_flag = 'Yes' THEN 1 ELSE 0 END) * 100.0 /
            NULLIF(COUNT(*), 0),
            2
        ) AS delay_rate_percent
        FROM logistics l
        JOIN orders o ON l.order_id = o.order_id
        WHERE o.platform_id = ?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: What is Blinkit's average delivery distance?
    query = """
    SELECT ROUND(COALESCE(AVG(l.distance_km), 0), 2) AS average_distance_km
        FROM logistics l
        JOIN orders o ON l.order_id = o.order_id
        WHERE o.platform_id = ?
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: What is Blinkit's average delivery rating?
    query = """
    SELECT ROUND(COALESCE(AVG(l.delivery_rating), 0), 2) AS average_delivery_rating
        FROM logistics l
        JOIN orders o ON l.order_id = o.order_id
        WHERE o.platform_id = ?
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: What is the average distance by vehicle type for Blinkit?
    query = """
    SELECT
            l.vehicle_type,
            ROUND(COALESCE(AVG(l.distance_km), 0), 2) AS average_distance_km
        FROM logistics l
        JOIN orders o ON l.order_id = o.order_id
        WHERE o.platform_id = ?
        GROUP BY l.vehicle_type
        ORDER BY average_distance_km DESC
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: How many Blinkit deliveries were delayed?
    query = """
    SELECT COUNT(*) AS delayed_deliveries
        FROM logistics l
        JOIN orders o ON l.order_id = o.order_id
        WHERE o.platform_id = ?
          AND l.delay_flag = 'Yes'
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Delay Rate",
            "Average Delivery Distance",
            "Average Delivery Rating",
            "Average Distance by Vehicle",
            "Delayed Deliveries",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which cities have the highest delivery delays?
    show_question(1, "Which cities have the highest delivery delays?")

    query = """
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
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "city",
        "delay_rate_percent",
        "Which cities have the highest delivery delays?",
        horizontal=True,
    )

    # Question 2: Does delivery distance explain delays?
    show_question(2, "Does delivery distance explain delays?")

    query = """
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
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_2_result,
        "vehicle_type",
        "delay_rate_percent",
        "Does delivery distance explain delays?",
        horizontal=True,
    )

    # Question 3: Which vehicle type is most efficient?
    show_question(3, "Which vehicle type is most efficient?")

    query = """
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
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_3_result,
        "distance_band",
        "delay_rate_percent",
        "Which vehicle type is most efficient?",
        horizontal=False,
    )

    # Question 4: Which cities receive poor delivery ratings?
    show_question(4, "Which cities receive poor delivery ratings?")

    query = """
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
    """
    question_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_4_result = apply_dashboard_filters(
        question_4_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_4_result,
        "city",
        "average_rating",
        "Which cities receive poor delivery ratings?",
        horizontal=True,
    )

    # Question 5: How can Blinkit improve delivery reliability?
    show_question(5, "How can Blinkit improve delivery reliability?")

    query = """
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
    """
    question_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_5_result = apply_dashboard_filters(
        question_5_result
    )

    # CHART TYPE: BAR CHART FOR CITY + VEHICLE COMBINATIONS
    logistics_chart = question_5_result.copy()

    if (
        not logistics_chart.empty
        and "city" in logistics_chart.columns
        and "vehicle_type" in logistics_chart.columns
    ):
        logistics_chart["city_vehicle"] = (
            logistics_chart["city"].astype(str)
            + " — "
            + logistics_chart["vehicle_type"].astype(str)
        )
    elif not logistics_chart.empty:
        logistics_chart["city_vehicle"] = (
            logistics_chart.index.astype(str)
        )

    draw_bar_chart(
        logistics_chart,
        "city_vehicle",
        "delay_rate_percent",
        "How can Blinkit improve delivery reliability?",
        horizontal=True,
    )


def render_blinkit_monthly_p_l():

    # ========================================================
    # 10. BLINKIT — MONTHLY P&L
    # ========================================================

    show_section_header(
        "Blinkit — Monthly P&L",
        "Revenue, COGS, operating costs, profit and monthly margin trends.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: What is Blinkit's P&L revenue?
    query = """
    SELECT ROUND(COALESCE(SUM(revenue_inr), 0), 2) AS revenue
        FROM pnl_monthly
        WHERE platform_id = ?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: What is Blinkit's P&L COGS?
    query = """
    SELECT ROUND(COALESCE(SUM(cogs_inr), 0), 2) AS cogs
        FROM pnl_monthly
        WHERE platform_id = ?
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: What is Blinkit's total operating cost?
    query = """
    SELECT ROUND(
            COALESCE(SUM(delivery_cost_inr), 0)
            + COALESCE(SUM(marketing_spend_inr), 0)
            + COALESCE(SUM(employee_cost_inr), 0)
            + COALESCE(SUM(other_opex_inr), 0),
            2
        ) AS total_operating_cost
        FROM pnl_monthly
        WHERE platform_id = ?
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: What is Blinkit's profit?
    query = """
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
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: What is Blinkit's profit margin percentage?
    query = """
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
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Revenue",
            "COGS",
            "Operating Cost",
            "Profit",
            "Profit Margin",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which cities generate the most revenue?
    show_question(1, "Which cities generate the most revenue?")

    query = """
    SELECT
            city,
            ROUND(COALESCE(SUM(revenue_inr), 0), 2) AS revenue
        FROM pnl_monthly
        WHERE platform_id = ?
        GROUP BY city
        ORDER BY revenue DESC
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "city",
        "revenue",
        "Which cities generate the most revenue?",
        horizontal=True,
    )

    # Question 2: Which cities are most profitable?
    show_question(2, "Which cities are most profitable?")

    query = """
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
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_2_result,
        "city",
        "profit",
        "Which cities are most profitable?",
        horizontal=True,
    )

    # Question 3: Which costs hurt Blinkit's margin the most?
    show_question(3, "Which costs hurt Blinkit's margin the most?")

    query = """
    SELECT
            ROUND(COALESCE(SUM(cogs_inr), 0), 2) AS cogs,
            ROUND(COALESCE(SUM(delivery_cost_inr), 0), 2) AS delivery_cost,
            ROUND(COALESCE(SUM(marketing_spend_inr), 0), 2) AS marketing_spend,
            ROUND(COALESCE(SUM(employee_cost_inr), 0), 2) AS employee_cost,
            ROUND(COALESCE(SUM(other_opex_inr), 0), 2) AS other_opex
        FROM pnl_monthly
        WHERE platform_id = ?
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_cost_chart(
        question_3_result,
        "Which costs hurt Blinkit's margin the most?",
    )

    # Question 4: Is marketing spend efficient?
    show_question(4, "Is marketing spend efficient?")

    query = """
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
    """
    question_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_4_result = apply_dashboard_filters(
        question_4_result
    )

    # CHART TYPE: LINE CHART
    draw_line_chart(
        question_4_result,
        "month",
        "revenue_per_marketing_rupee",
        "Is Marketing Spend Efficient?",
    )

    # Question 5: How does Blinkit's profit trend over time?
    show_question(5, "How does Blinkit's profit trend over time?")

    query = """
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
    """
    question_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_5_result = apply_dashboard_filters(
        question_5_result
    )

    # CHART TYPE: LINE CHART
    color_column = None

    draw_line_chart(
        question_5_result,
        "month",
        "profit",
        "How does Blinkit's profit trend over time?",
        color_column=color_column,
    )


# ============================================================
# SWIGGY INSTAMART — FULL QUERY-BY-QUERY DASHBOARD
# ============================================================

def render_swiggy_instamart_overview():

    # ========================================================
    # 1. SWIGGY INSTAMART — OVERVIEW
    # ========================================================

    show_section_header(
        "Swiggy Instamart — Overview",
        "Executive snapshot of business scale, growth, customer economics, operations and profitability.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: Revenue
    query = """
    SELECT ROUND(SUM(order_value_inr), 2) AS revenue
        FROM orders
        WHERE platform_id = ?
          AND order_value_inr IS NOT NULL
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: Orders
    query = """
    SELECT COUNT(*) AS orders
        FROM orders
        WHERE platform_id = ?
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: Average Order Value (AOV)
    query = """
    SELECT ROUND(AVG(order_value_inr), 2) AS aov
        FROM orders
        WHERE platform_id = ?
          AND order_value_inr IS NOT NULL
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: Profit Margin
    query = """
    SELECT ROUND(
            SUM(profit_inr) * 100.0 / NULLIF(SUM(revenue_inr), 0),
            2
        ) AS profit_margin_percent
        FROM pnl_monthly_safe
        WHERE platform_id = ?
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: Discount Rate
    query = """
    SELECT ROUND(
            SUM(COALESCE(discount_inr, 0)) * 100.0
            / NULLIF(SUM(COALESCE(order_value_inr, 0)), 0),
            2
        ) AS discount_rate_percent
        FROM orders
        WHERE platform_id = ?
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Revenue",
            "Orders",
            "Average Order Value (AOV)",
            "Profit Margin",
            "Discount Rate",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which cities drive Instamart's growth?
    show_question(1, "Which cities drive Instamart's growth?")

    query = """
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
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "platform_name",
        "total_revenue",
        "Which cities drive Instamart's growth?",
        horizontal=True,
    )

    # Question 2: Which cities are profitable?
    show_question(2, "Which cities are profitable?")

    query = """
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
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: LINE CHART
    color_column = None

    draw_line_chart(
        question_2_result,
        "year",
        "revenue",
        "Which cities are profitable?",
        color_column=color_column,
    )

    # Question 3: Which cities have weak unit economics?
    show_question(3, "Which cities have weak unit economics?")

    query = """
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
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id] * 2,
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_3_result,
        "city",
        "revenue",
        "Which cities have weak unit economics?",
        horizontal=True,
    )

def render_swiggy_instamart_store():

    # ========================================================
    # 2. SWIGGY INSTAMART — STORE
    # ========================================================

    show_section_header(
        "Swiggy Instamart — Store",
        "Store network size, productivity, utilization and capacity decisions.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: Store Count
    query = """
    SELECT COUNT(*) AS store_count
        FROM dark_stores
        WHERE platform_id = ?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: Orders per Store
    query = """
    SELECT ROUND(
            (SELECT COUNT(*) FROM orders WHERE platform_id = ?) * 1.0
            / NULLIF(
                (SELECT COUNT(*) FROM dark_stores WHERE platform_id = ?),
                0
            ),
            2
        ) AS orders_per_store
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id] * 2,
    )

    # KPI 3: Average Store Size
    query = """
    SELECT ROUND(AVG(sqft_area), 2) AS average_store_size_sqft
        FROM dark_stores
        WHERE platform_id = ?
          AND sqft_area IS NOT NULL
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: Store Productivity
    query = """
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
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id] * 2,
    )

    # KPI 5: Store Contribution
    query = """
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
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id] * 2,
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Store Count",
            "Orders per Store",
            "Average Store Size",
            "Store Productivity",
            "Store Contribution",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which Instamart stores lead in orders?
    show_question(1, "Which Instamart stores lead in orders?")

    query = """
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
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id] * 2,
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "store_name",
        "orders",
        "Which Instamart stores lead in orders?",
        horizontal=True,
    )

    # Question 2: Which stores underperform?
    show_question(2, "Which stores underperform?")

    query = """
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
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id] * 2,
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_2_result,
        "store_name",
        "orders_per_sqft",
        "Which stores underperform?",
        horizontal=True,
    )

    # Question 3: Which cities require more stores?
    show_question(3, "Which cities require more stores?")

    query = """
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
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id] * 2,
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_3_result,
        "city",
        "orders_per_store",
        "Which cities require more stores?",
        horizontal=True,
    )

def render_swiggy_instamart_employee():

    # ========================================================
    # 3. SWIGGY INSTAMART — EMPLOYEE
    # ========================================================

    show_section_header(
        "Swiggy Instamart — Employee",
        "Workforce size, staffing balance, salary cost and productivity.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: Total Workforce
    query = """
    SELECT COUNT(*) AS total_workforce
        FROM employees e
        JOIN dark_stores ds
            ON e.store_id = ds.store_id
        WHERE ds.platform_id = ?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: Active Employees
    query = """
    SELECT COUNT(*) AS active_employees
        FROM employees e
        JOIN dark_stores ds
            ON e.store_id = ds.store_id
        WHERE ds.platform_id = ?
          AND e.work_status = 'Currently Working'
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: Average Salary
    query = """
    SELECT ROUND(AVG(e.monthly_salary_inr), 2) AS average_salary
        FROM employees e
        JOIN dark_stores ds
            ON e.store_id = ds.store_id
        WHERE ds.platform_id = ?
          AND e.monthly_salary_inr IS NOT NULL
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: Employees per Store
    query = """
    SELECT ROUND(
            COUNT(e.employee_id) * 1.0
            / NULLIF(COUNT(DISTINCT ds.store_id), 0),
            2
        ) AS employees_per_store
        FROM dark_stores ds
        LEFT JOIN employees e
            ON ds.store_id = e.store_id
        WHERE ds.platform_id = ?
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: Employee Cost per Order
    query = """
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
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id] * 2,
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Total Workforce",
            "Active Employees",
            "Average Salary",
            "Employees per Store",
            "Employee Cost per Order",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which stores have the highest staffing levels?
    show_question(1, "Which stores have the highest staffing levels?")

    query = """
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
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "store_name",
        "employee_count",
        "Which stores have the highest staffing levels?",
        horizontal=True,
    )

    # Question 2: Which stores are understaffed?
    show_question(2, "Which stores are understaffed?")

    query = """
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
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id] * 3,
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_2_result,
        "store_name",
        "orders_per_employee",
        "Which stores are understaffed?",
        horizontal=True,
    )

    # Question 3: Which roles cost the most?
    show_question(3, "Which roles cost the most?")

    query = """
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
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_3_result,
        "role",
        "total_monthly_cost",
        "Which roles cost the most?",
        horizontal=True,
    )

def render_swiggy_instamart_product():

    # ========================================================
    # 4. SWIGGY INSTAMART — PRODUCT
    # ========================================================

    show_section_header(
        "Swiggy Instamart — Product",
        "Catalogue size, category mix, brands, discounts and pricing decisions.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: Product Count
    query = """
    SELECT COUNT(DISTINCT oi.product_id) AS product_count
        FROM order_items oi
        JOIN orders o
            ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: Average Selling Price
    query = """
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
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: Discount %
    query = """
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
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: Category Count
    query = """
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
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: Price Outlier Count
    query = """
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
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Product Count",
            "Average Selling Price",
            "Discount %",
            "Category Count",
            "Price Outlier Count",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which categories dominate Instamart's assortment?
    show_question(1, "Which categories dominate Instamart's assortment?")

    query = """
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
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "category",
        "product_count",
        "Which categories dominate Instamart's assortment?",
        horizontal=True,
    )

    # Question 2: Which products are highly discounted?
    show_question(2, "Which products are highly discounted?")

    query = """
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
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_2_result,
        "product_name",
        "discount_percent",
        "Which products are highly discounted?",
        horizontal=True,
    )

    # Question 3: Which products have unusually high prices?
    show_question(3, "Which products have unusually high prices?")

    query = """
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
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_3_result,
        "product_name",
        "selling_price",
        "Which products have unusually high prices?",
        horizontal=True,
    )

def render_swiggy_instamart_customer():

    # ========================================================
    # 5. SWIGGY INSTAMART — CUSTOMER
    # ========================================================

    show_section_header(
        "Swiggy Instamart — Customer",
        "Customer base, acquisition, geography, signup and app mix.",
    )

    # --------------------------------------------------------
    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: Total Customers
    query = """
    SELECT
        COUNT(DISTINCT c.customer_id) AS total_customers
    FROM customers c
    WHERE LOWER(TRIM(c.signup_platform)) = 'swiggy instamart'
    """
    kpi_1_result = fetch_data(
        query,
        [],
    )

    # KPI 2: Active Customers
    # Customers from the platform signup base who have
    # placed at least one order on the selected platform.
    query = """
    SELECT
        COUNT(DISTINCT o.customer_id) AS active_customers
    FROM orders o
    INNER JOIN customers c
        ON o.customer_id = c.customer_id
    WHERE o.platform_id = ?
      AND LOWER(TRIM(c.signup_platform)) = 'swiggy instamart'
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: Customer Activation Rate
    # Active Customers / Total Customers * 100
    query = """
    WITH platform_customers AS (
        SELECT DISTINCT
            c.customer_id
        FROM customers c
        WHERE LOWER(TRIM(c.signup_platform)) = 'swiggy instamart'
    ),
    active_customers AS (
        SELECT DISTINCT
            o.customer_id
        FROM orders o
        INNER JOIN platform_customers pc
            ON o.customer_id = pc.customer_id
        WHERE o.platform_id = ?
    )
    SELECT
        ROUND(
            COUNT(DISTINCT ac.customer_id) * 100.0
            / NULLIF(
                COUNT(DISTINCT pc.customer_id),
                0
            ),
            2
        ) AS activation_rate_percent
    FROM platform_customers pc
    LEFT JOIN active_customers ac
        ON pc.customer_id = ac.customer_id
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: Orders per Customer
    # Total platform orders / Active Customers
    query = """
    WITH platform_customers AS (
        SELECT DISTINCT
            c.customer_id
        FROM customers c
        WHERE LOWER(TRIM(c.signup_platform)) = 'swiggy instamart'
    ),
    active_customers AS (
        SELECT DISTINCT
            o.customer_id
        FROM orders o
        INNER JOIN platform_customers pc
            ON o.customer_id = pc.customer_id
        WHERE o.platform_id = ?
    ),
    platform_orders AS (
        SELECT
            COUNT(DISTINCT o.order_id) AS total_orders
        FROM orders o
        INNER JOIN platform_customers pc
            ON o.customer_id = pc.customer_id
        WHERE o.platform_id = ?
    )
    SELECT
        ROUND(
            po.total_orders * 1.0
            / NULLIF(
                COUNT(DISTINCT ac.customer_id),
                0
            ),
            2
        ) AS orders_per_customer
    FROM active_customers ac
    CROSS JOIN platform_orders po
    """
    kpi_4_result = fetch_data(
        query,
        [
            selected_platform_id,
            selected_platform_id,
        ],
    )

    # KPI 5: Repeat Customer Rate
    # Customers with more than one order / Active Customers * 100
    query = """
    WITH platform_customers AS (
        SELECT DISTINCT
            c.customer_id
        FROM customers c
        WHERE LOWER(TRIM(c.signup_platform)) = 'swiggy instamart'
    ),
    customer_order_counts AS (
        SELECT
            o.customer_id,
            COUNT(DISTINCT o.order_id) AS order_count
        FROM orders o
        INNER JOIN platform_customers pc
            ON o.customer_id = pc.customer_id
        WHERE o.platform_id = ?
        GROUP BY o.customer_id
    )
    SELECT
        ROUND(
            SUM(
                CASE
                    WHEN order_count > 1
                    THEN 1
                    ELSE 0
                END
            ) * 100.0
            / NULLIF(
                COUNT(customer_id),
                0
            ),
            2
        ) AS repeat_customer_rate_percent
    FROM customer_order_counts
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Total Customers",
            "Active Customers",
            "Customer Activation Rate",
            "Orders per Customer",
            "Repeat Customer Rate",
        ],
    )

    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which cities have the largest Instamart customer base?
    show_question(1, "Which cities have the largest Instamart customer base?")

    query = """
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
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "city",
        "customer_count",
        "Which cities have the largest Instamart customer base?",
        horizontal=True,
    )

    # Question 2: Where is customer acquisition weak?
    show_question(2, "Where is customer acquisition weak?")

    query = """
    SELECT
            c.city,
            COUNT(DISTINCT c.customer_id) AS customers_acquired
        FROM customers c
        WHERE LOWER(TRIM(c.signup_platform)) = 'swiggy instamart'
        GROUP BY c.city
        ORDER BY customers_acquired ASC
        LIMIT 15
    """
    question_2_result = fetch_data(
        query,
        [],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: HORIZONTAL BAR CHART
    draw_bar_chart(
        question_2_result,
        "city",
        "new_customers",
        "Where is Customer Acquisition Weak?",
        horizontal=True,
    )

    # Question 3: Which signup platform contributes most customers?
    show_question(3, "Which signup platform contributes most customers?")

    query = """
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
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_3_result,
        "signup_platform",
        "customers",
        "Which Signup Platform Contributes Most Customers?",
        horizontal=True,
    )

def render_swiggy_instamart_orders():

    # ========================================================
    # 6. SWIGGY INSTAMART — ORDERS
    # ========================================================

    show_section_header(
        "Swiggy Instamart — Orders",
        "Order volume, AOV, completion, cancellations, returns and payment behavior.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: Orders
    query = """
    SELECT COUNT(*) AS orders
        FROM orders
        WHERE platform_id = ?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: AOV
    query = """
    SELECT ROUND(AVG(order_value_inr), 2) AS aov
        FROM orders
        WHERE platform_id = ?
          AND order_value_inr IS NOT NULL
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: Delivered %
    query = """
    SELECT ROUND(
            SUM(
                CASE WHEN LOWER(order_status) = 'delivered'
                     THEN 1 ELSE 0 END
            ) * 100.0 / NULLIF(COUNT(*), 0),
            2
        ) AS delivered_percent
        FROM orders
        WHERE platform_id = ?
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: Cancellation %
    query = """
    SELECT ROUND(
            SUM(
                CASE WHEN LOWER(order_status) = 'cancelled'
                     THEN 1 ELSE 0 END
            ) * 100.0 / NULLIF(COUNT(*), 0),
            2
        ) AS cancellation_percent
        FROM orders
        WHERE platform_id = ?
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: Return %
    query = """
    SELECT ROUND(
            SUM(
                CASE WHEN LOWER(order_status) = 'returned'
                     THEN 1 ELSE 0 END
            ) * 100.0 / NULLIF(COUNT(*), 0),
            2
        ) AS return_percent
        FROM orders
        WHERE platform_id = ?
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Orders",
            "AOV",
            "Delivered %",
            "Cancellation %",
            "Return %",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which cities contribute most orders?
    show_question(1, "Which cities contribute most orders?")

    query = """
    SELECT
            ds.city,
            COUNT(o.order_id) AS orders
        FROM orders o
        JOIN dark_stores ds
            ON o.store_id = ds.store_id
        WHERE o.platform_id = ?
        GROUP BY ds.city
        ORDER BY orders DESC
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "city",
        "total_orders",
        "Which cities contribute most orders?",
        horizontal=True,
    )

    # Question 2: Where are cancellation rates highest?
    show_question(2, "Where are cancellation rates highest?")

    query = """
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
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_2_result,
        "city",
        "cancellation_rate_percent",
        "Where are cancellation rates highest?",
        horizontal=True,
    )

    # Question 3: Where are returns highest?
    show_question(3, "Where are returns highest?")

    query = """
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
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_3_result,
        "store_name",
        "total_orders",
        "Where are returns highest?",
        horizontal=True,
    )

def render_swiggy_instamart_order_items():

    # ========================================================
    # 7. SWIGGY INSTAMART — ORDER ITEMS
    # ========================================================

    show_section_header(
        "Swiggy Instamart — Order Items",
        "Product demand, basket composition, item value and basket growth.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: Units Sold
    query = """
    SELECT SUM(COALESCE(oi.quantity, 0)) AS units_sold
        FROM order_items oi
        JOIN orders o
            ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: Item Value
    query = """
    SELECT ROUND(
            SUM(COALESCE(oi.line_total_inr, 0)),
            2
        ) AS item_value
        FROM order_items oi
        JOIN orders o
            ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: Average Item Price
    query = """
    SELECT ROUND(AVG(oi.item_price_inr), 2) AS average_item_price
        FROM order_items oi
        JOIN orders o
            ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
          AND oi.item_price_inr IS NOT NULL
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: Basket Size
    query = """
    SELECT ROUND(
            SUM(COALESCE(oi.quantity, 0)) * 1.0
            / NULLIF(COUNT(DISTINCT oi.order_id), 0),
            2
        ) AS average_basket_size
        FROM order_items oi
        JOIN orders o
            ON oi.order_id = o.order_id
        WHERE o.platform_id = ?
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: Product Contribution
    query = """
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
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Units Sold",
            "Item Value",
            "Average Item Price",
            "Basket Size",
            "Product Contribution",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which products sell the most units?
    show_question(1, "Which products sell the most units?")

    query = """
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
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "product_name",
        "units_sold",
        "Which products sell the most units?",
        horizontal=True,
    )

    # Question 2: Which products create the most value?
    show_question(2, "Which products create the most value?")

    query = """
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
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_2_result,
        "product_name",
        "item_value",
        "Which products create the most value?",
        horizontal=True,
    )

    # Question 3: Which categories dominate customer baskets?
    show_question(3, "Which categories dominate customer baskets?")

    query = """
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
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: DONUT / PIE CHART
    draw_pie_chart(
        question_3_result,
        "category",
        "item_value",
        "Which categories dominate customer baskets?",
    )

def render_swiggy_instamart_inventory():

    # ========================================================
    # 8. SWIGGY INSTAMART — INVENTORY
    # ========================================================

    show_section_header(
        "Swiggy Instamart — Inventory",
        "Stock levels, reorder risk, expiry risk, overstock and working capital.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: Stock Units
    query = """
    SELECT SUM(COALESCE(i.stock_units, 0)) AS stock_units
        FROM inventory i
        JOIN dark_stores ds
            ON i.store_id = ds.store_id
        WHERE ds.platform_id = ?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: Low-stock SKUs
    query = """
    SELECT COUNT(*) AS low_stock_skus
        FROM inventory i
        JOIN dark_stores ds
            ON i.store_id = ds.store_id
        WHERE ds.platform_id = ?
          AND COALESCE(i.stock_units, 0)
              <= COALESCE(i.reorder_level, 0)
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: Reorder Risk
    query = """
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
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: Expiry Risk
    query = """
    SELECT SUM(COALESCE(i.stock_units, 0)) AS expiry_risk_units
        FROM inventory i
        JOIN dark_stores ds
            ON i.store_id = ds.store_id
        WHERE ds.platform_id = ?
          AND i.expiry_date IS NOT NULL
          AND DATE(i.expiry_date) <= DATE('now', '+30 day')
          AND COALESCE(i.stock_units, 0) > 0
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: Stock per Store
    query = """
    SELECT ROUND(
            SUM(COALESCE(i.stock_units, 0)) * 1.0
            / NULLIF(COUNT(DISTINCT ds.store_id), 0),
            2
        ) AS stock_per_store
        FROM inventory i
        JOIN dark_stores ds
            ON i.store_id = ds.store_id
        WHERE ds.platform_id = ?
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Stock Units",
            "Low-stock SKUs",
            "Reorder Risk",
            "Expiry Risk",
            "Stock per Store",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which stores have the highest stockout risk?
    show_question(1, "Which stores have the highest stockout risk?")

    query = """
    SELECT
            ds.store_id,
            COALESCE(ds.store_name_clean, ds.store_name) AS store_name,
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
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "store_name",
        "stockout_risk_percent",
        "Which stores have the highest stockout risk?",
        horizontal=True,
    top_n=8,
)

    # Question 2: Which products are below reorder levels?
    show_question(2, "Which products are below reorder levels?")

    query = """
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
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: GROUPED BAR CHART
    draw_metric_comparison(
        question_2_result,
        "product_name",
        ["stock_units", "reorder_level"],
        "Which products are below reorder levels?",
    )

    # Question 3: Where is inventory excessive?
    show_question(3, "Where is inventory excessive?")

    query = """
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
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_metric_comparison(
        question_3_result,
        "product_name",
        ["stock_units", "reorder_level"],
        "Stock vs Reorder Level — Excess Inventory",
    )

def render_swiggy_instamart_logistics():

    # ========================================================
    # 9. SWIGGY INSTAMART — LOGISTICS
    # ========================================================

    show_section_header(
        "Swiggy Instamart — Logistics",
        "Delays, distance, ratings, vehicle performance and delivery optimization.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: Delay Rate
    query = """
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
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: Delivery Rating
    query = """
    SELECT ROUND(AVG(l.delivery_rating), 2) AS delivery_rating
        FROM logistics l
        JOIN orders o
            ON l.order_id = o.order_id
        WHERE o.platform_id = ?
          AND l.delivery_rating IS NOT NULL
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: Average Distance
    query = """
    SELECT ROUND(AVG(l.distance_km), 2) AS average_distance_km
        FROM logistics l
        JOIN orders o
            ON l.order_id = o.order_id
        WHERE o.platform_id = ?
          AND l.distance_km IS NOT NULL
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: Delayed Orders
    query = """
    SELECT COUNT(*) AS delayed_orders
        FROM logistics l
        JOIN orders o
            ON l.order_id = o.order_id
        WHERE o.platform_id = ?
          AND LOWER(l.delay_flag) IN ('yes', 'y')
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: Vehicle Mix
    query = """
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
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Delay Rate",
            "Delivery Rating",
            "Average Distance",
            "Delayed Orders",
            "Vehicle Mix",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which cities experience the most delays?
    show_question(1, "Which cities experience the most delays?")

    query = """
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
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "city",
        "delay_rate_percent",
        "Which cities experience the most delays?",
        horizontal=True,
    )

    # Question 2: Which vehicle types perform best?
    show_question(2, "Which vehicle types perform best?")

    query = """
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
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_2_result,
        "vehicle_type",
        "delay_rate_percent",
        "Which vehicle types perform best?",
        horizontal=True,
    )

    # Question 3: Does longer distance reduce delivery performance?
    show_question(3, "Does longer distance reduce delivery performance?")

    query = """
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
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_3_result,
        "distance_band",
        "delay_rate_percent",
        "Does longer distance reduce delivery performance?",
        horizontal=False,
    )

    # Question 4: How can delivery reliability be improved?
    show_question(4, "How can delivery reliability be improved?")

    query = """
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
    """
    question_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_5_result = apply_dashboard_filters(
        question_5_result
    )

    # CHART TYPE: BAR CHART FOR CITY + VEHICLE COMBINATIONS
    logistics_chart = question_5_result.copy()

    if (
        not logistics_chart.empty
        and "city" in logistics_chart.columns
        and "vehicle_type" in logistics_chart.columns
    ):
        logistics_chart["city_vehicle"] = (
            logistics_chart["city"].astype(str)
            + " — "
            + logistics_chart["vehicle_type"].astype(str)
        )
    elif not logistics_chart.empty:
        logistics_chart["city_vehicle"] = (
            logistics_chart.index.astype(str)
        )

    draw_bar_chart(
        logistics_chart,
        "city_vehicle",
        "delay_rate_percent",
        "How can delivery reliability be improved?",
        horizontal=True,
    )


def render_swiggy_instamart_monthly_p_l():

    # ========================================================
    # 10. SWIGGY INSTAMART — MONTHLY P&L
    # ========================================================

    show_section_header(
        "Swiggy Instamart — Monthly P&L",
        "Revenue, COGS, operating costs, profit and monthly margin trends.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: Revenue
    query = """
    SELECT ROUND(SUM(revenue_inr), 2) AS revenue
        FROM pnl_monthly_safe
        WHERE platform_id = ?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: COGS
    query = """
    SELECT ROUND(SUM(cogs_inr), 2) AS cogs
        FROM pnl_monthly_safe
        WHERE platform_id = ?
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: Operating Cost
    query = """
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
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: Profit
    query = """
    SELECT ROUND(SUM(profit_inr), 2) AS profit
        FROM pnl_monthly_safe
        WHERE platform_id = ?
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: Margin %
    query = """
    SELECT ROUND(
            SUM(profit_inr) * 100.0
            / NULLIF(SUM(revenue_inr), 0),
            2
        ) AS margin_percent
        FROM pnl_monthly_safe
        WHERE platform_id = ?
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Revenue",
            "COGS",
            "Operating Cost",
            "Profit",
            "Margin %",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which cities are most profitable?
    show_question(1, "Which cities are most profitable?")

    query = """
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
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "city",
        "revenue",
        "Which cities are most profitable?",
        horizontal=True,
    )

    # Question 2: Which cities have poor margins?
    show_question(2, "Which cities have poor margins?")

    query = """
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
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_2_result,
        "city",
        "margin_percent",
        "Which cities have poor margins?",
        horizontal=True,
    )

    # Question 3: Which cost category is growing fastest?
    show_question(3, "Which cost category is growing fastest?")

    query = """
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
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_metric_comparison(
        question_3_result,
        "month",
        ["cogs", "delivery_cost", "marketing_spend", "employee_cost", "other_opex"],
        "Monthly Operating Cost Categories",
    )

    # Question 4: Is marketing spend generating sufficient revenue?
    show_question(4, "Is marketing spend generating sufficient revenue?")

    query = """
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
    """
    question_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_4_result = apply_dashboard_filters(
        question_4_result
    )

    # CHART TYPE: LINE CHART
    draw_line_chart(
        question_4_result,
        "month",
        "revenue_per_marketing_rupee",
        "Is Marketing Spend Generating Sufficient Revenue?",
    )

    # Question 5: How is profitability changing monthly?
    show_question(5, "How is profitability changing monthly?")

    query = """
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
    """
    question_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_5_result = apply_dashboard_filters(
        question_5_result
    )

    # CHART TYPE: LINE CHART
    color_column = None

    draw_line_chart(
        question_5_result,
        "month",
        "profit",
        "How is profitability changing monthly?",
        color_column=color_column,
    )


# ============================================================
# BIGBASKET — FULL QUERY-BY-QUERY DASHBOARD
# ============================================================

def render_bigbasket_overview():

    # ========================================================
    # 1. BIGBASKET — OVERVIEW
    # ========================================================

    show_section_header(
        "BigBasket — Overview",
        "Executive snapshot of business scale, growth, customer economics, operations and profitability.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: What is BigBasket's total revenue?
    query = """
    SELECT ROUND(SUM(revenue_inr),2) AS total_revenue
    FROM pnl_monthly_safe WHERE platform_id=?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: What is BigBasket's total number of orders?
    query = """
    SELECT COUNT(order_id) AS total_orders FROM orders WHERE platform_id=?
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: What is BigBasket's AOV?
    query = """
    SELECT ROUND(AVG(order_value_inr),2) AS aov_inr
    FROM orders WHERE platform_id=?
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: What is BigBasket's discount rate?
    query = """
    SELECT ROUND(
        SUM(COALESCE(discount_inr,0))*100.0 /
        NULLIF(SUM(COALESCE(order_value_inr,0))+SUM(COALESCE(discount_inr,0)),0),2
    ) AS discount_rate_percent
    FROM orders WHERE platform_id=?
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: What is BigBasket's profit margin?
    query = """
    SELECT ROUND(SUM(profit_inr)*100.0/NULLIF(SUM(revenue_inr),0),2) AS profit_margin_percent
    FROM pnl_monthly_safe WHERE platform_id=?
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Total Revenue",
            "Total Orders",
            "AOV",
            "Discount Rate",
            "Profit Margin",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which cities are BigBasket's strongest markets?
    show_question(1, "Which cities are BigBasket's strongest markets?")

    query = """
    SELECT ds.city, COUNT(o.order_id) AS total_orders, ROUND(SUM(o.order_value_inr),2) AS order_value
    FROM orders o JOIN dark_stores ds ON o.store_id=ds.store_id WHERE o.platform_id=? GROUP BY ds.city
    ORDER BY total_orders DESC, order_value DESC
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "city",
        "order_value",
        "Which cities are BigBasket's strongest markets?",
        horizontal=True,
    )

    # Question 2: Where is BigBasket losing business?
    show_question(2, "Where is BigBasket losing business?")

    query = """
    SELECT ds.city, COUNT(o.order_id) AS total_orders,
    ROUND(SUM(CASE WHEN LOWER(TRIM(o.order_status)) IN ('cancelled','returned') THEN 1 ELSE 0 END)*100.0/COUNT(o.order_id),2) AS problem_order_rate_percent
    FROM orders o JOIN dark_stores ds ON o.store_id=ds.store_id WHERE o.platform_id=? GROUP BY ds.city
    ORDER BY problem_order_rate_percent DESC
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: HORIZONTAL BAR CHART
    draw_bar_chart(
        question_2_result,
        "city",
        "problem_order_rate_percent",
        "Where is BigBasket Losing Business?",
        horizontal=True,
    )

    # Question 3: Is growth driven more by customers or order frequency?
    show_question(3, "Is growth driven more by customers or order frequency?")

    query = """
    SELECT strftime('%Y-%m',order_datetime) AS month,
    COUNT(order_id) AS orders,
    COUNT(DISTINCT customer_id) AS active_customers,
    ROUND(COUNT(order_id)*1.0/NULLIF(COUNT(DISTINCT customer_id),0),2) AS orders_per_customer
    FROM orders WHERE platform_id=? AND order_datetime IS NOT NULL
    GROUP BY strftime('%Y-%m',order_datetime) ORDER BY month
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: LINE CHART
    draw_line_chart(
        question_3_result,
        "month",
        "orders_per_customer",
        "Is Growth Driven More by Customers or Order Frequency?",
    )

def render_bigbasket_store():

    # ========================================================
    # 2. BIGBASKET — STORE
    # ========================================================

    show_section_header(
        "BigBasket — Store",
        "Store network size, productivity, utilization and capacity decisions.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: How many BigBasket stores are there?
    query = """
    SELECT COUNT(DISTINCT store_id) AS store_count
    FROM orders WHERE platform_id=?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: What are BigBasket's orders per store?
    query = """
    SELECT ROUND(COUNT(order_id)*1.0/NULLIF(COUNT(DISTINCT store_id),0),2) AS orders_per_store
    FROM orders WHERE platform_id=?
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: What is the average BigBasket store size?
    query = """
    SELECT ROUND(AVG(sqft_area),2) AS average_store_size_sqft
    FROM dark_stores WHERE store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=?)
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: What is BigBasket's store productivity?
    query = """
    SELECT ROUND(COUNT(o.order_id)*1.0/NULLIF(SUM(ds.sqft_area),0),4) AS orders_per_sqft
    FROM dark_stores ds JOIN orders o ON ds.store_id=o.store_id
    WHERE o.platform_id=?
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: What is each store's BigBasket contribution?
    query = """
    SELECT ds.store_id, ds.store_name, ds.city, COUNT(o.order_id) AS orders,
    ROUND(SUM(o.order_value_inr),2) AS order_value
    FROM dark_stores ds JOIN orders o ON ds.store_id=o.store_id
    WHERE o.platform_id=? GROUP BY ds.store_id,ds.store_name,ds.city
    ORDER BY order_value DESC
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Store Count",
            "Orders per Store",
            "Average Store Size",
            "Store Productivity",
            "Store Contribution",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which BigBasket stores perform best?
    show_question(1, "Which BigBasket stores perform best?")

    query = """
    SELECT ds.store_id,ds.store_name,ds.city,COUNT(o.order_id) AS orders,
    ROUND(AVG(o.order_value_inr),2) AS aov
    FROM dark_stores ds JOIN orders o ON ds.store_id=o.store_id
    WHERE o.platform_id=? GROUP BY ds.store_id,ds.store_name,ds.city
    ORDER BY orders DESC,aov DESC
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "store_name",
        "orders",
        "Which BigBasket stores perform best?",
        horizontal=True,
    )

    # Question 2: Which stores are underperforming?
    show_question(2, "Which stores are underperforming?")

    query = """
    SELECT ds.store_id,ds.store_name,ds.city,ds.sqft_area,COUNT(o.order_id) AS orders,
    ROUND(COUNT(o.order_id)*1.0/NULLIF(ds.sqft_area,0),4) AS orders_per_sqft
    FROM dark_stores ds LEFT JOIN orders o ON ds.store_id=o.store_id AND o.platform_id=?
    GROUP BY ds.store_id,ds.store_name,ds.city,ds.sqft_area
    ORDER BY orders ASC,orders_per_sqft ASC
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_2_result,
        "store_name",
        "orders_per_sqft",
        "Which stores are underperforming?",
        horizontal=True,
    )

    # Question 3: Which cities need more capacity?
    show_question(3, "Which cities need more capacity?")

    query = """
    SELECT ds.city,COUNT(o.order_id) AS orders,COUNT(DISTINCT o.store_id) AS stores,
    ROUND(COUNT(o.order_id)*1.0/NULLIF(COUNT(DISTINCT o.store_id),0),2) AS orders_per_store
    FROM orders o JOIN dark_stores ds ON o.store_id=ds.store_id WHERE o.platform_id=? GROUP BY ds.city
    ORDER BY orders_per_store DESC,orders DESC
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_3_result,
        "city",
        "orders_per_store",
        "Which cities need more capacity?",
        horizontal=True,
    )

def render_bigbasket_employee():

    # ========================================================
    # 3. BIGBASKET — EMPLOYEE
    # ========================================================

    show_section_header(
        "BigBasket — Employee",
        "Workforce size, staffing balance, salary cost and productivity.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: How many employees does BigBasket have?
    query = """
    SELECT COUNT(DISTINCT employee_id) AS total_employees FROM employees
    WHERE store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: How many active employees does BigBasket have?
    query = """
    SELECT COUNT(DISTINCT employee_id) AS active_employees FROM employees
    WHERE LOWER(TRIM(employment_status)) IN ('active','working')
    AND store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: What is BigBasket's average monthly salary?
    query = """
    SELECT ROUND(AVG(monthly_salary_inr),2) AS average_monthly_salary FROM employees
    WHERE store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: How many employees are there per store?
    query = """
    SELECT ROUND(COUNT(DISTINCT employee_id)*1.0/NULLIF(COUNT(DISTINCT store_id),0),2) AS employees_per_store
    FROM employees WHERE store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: What is employee cost per BigBasket order?
    query = """
    SELECT ROUND(
        (SELECT SUM(monthly_salary_inr) FROM employees
         WHERE store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=?)) * 1.0 /
        NULLIF((SELECT COUNT(order_id) FROM orders WHERE platform_id=?),0),2
    ) AS employee_cost_per_order
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id] * 2,
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Total Employees",
            "Active Employees",
            "Average Monthly Salary",
            "Employees per Store",
            "Employee Cost per Order",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which stores have the highest employee count?
    show_question(1, "Which stores have the highest employee count?")

    query = """
    SELECT e.store_id,ds.store_name,ds.city,COUNT(e.employee_id) AS employee_count
    FROM employees e JOIN dark_stores ds ON e.store_id=ds.store_id
    WHERE e.store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
    GROUP BY e.store_id,ds.store_name,ds.city ORDER BY employee_count DESC
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "store_name",
        "employee_count",
        "Which stores have the highest employee count?",
        horizontal=True,
    )

    # Question 2: Which stores are understaffed relative to order volume?
    show_question(2, "Which stores are understaffed relative to order volume?")

    query = """
    SELECT ds.store_id,ds.store_name,ds.city,COUNT(DISTINCT e.employee_id) AS employees,
    COUNT(DISTINCT o.order_id) AS orders,
    ROUND(COUNT(DISTINCT o.order_id)*1.0/NULLIF(COUNT(DISTINCT e.employee_id),0),2) AS orders_per_employee
    FROM dark_stores ds LEFT JOIN employees e ON ds.store_id=e.store_id
    LEFT JOIN orders o ON ds.store_id=o.store_id AND o.platform_id=?
    GROUP BY ds.store_id,ds.store_name,ds.city
    ORDER BY orders_per_employee DESC
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_2_result,
        "store_name",
        "orders_per_employee",
        "Which stores are understaffed relative to order volume?",
        horizontal=True,
    )

    # Question 3: Which employee roles have the highest cost?
    show_question(3, "Which employee roles have the highest cost?")

    query = """
    SELECT role,COUNT(employee_id) AS employees,ROUND(AVG(monthly_salary_inr),2) AS avg_salary,
    ROUND(SUM(monthly_salary_inr),2) AS total_monthly_cost
    FROM employees WHERE store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
    GROUP BY role ORDER BY total_monthly_cost DESC
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_3_result,
        "role",
        "total_monthly_cost",
        "Which employee roles have the highest cost?",
        horizontal=True,
    )

def render_bigbasket_product():

    # ========================================================
    # 4. BIGBASKET — PRODUCT
    # ========================================================

    show_section_header(
        "BigBasket — Product",
        "Catalogue size, category mix, brands, discounts and pricing decisions.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: How many products are in BigBasket's catalogue?
    query = """
    SELECT COUNT(DISTINCT product_id) AS product_count FROM products
    """
    kpi_1_result = fetch_data(
        query,
        [],
    )

    # KPI 2: What is BigBasket's average selling price?
    query = """
    SELECT ROUND(AVG(selling_price),2) AS average_selling_price FROM products
    """
    kpi_2_result = fetch_data(
        query,
        [],
    )

    # KPI 3: What is BigBasket's average product discount?
    query = """
    SELECT ROUND(AVG(discount_percent),2) AS average_discount_percent FROM products
    """
    kpi_3_result = fetch_data(
        query,
        [],
    )

    # KPI 4: What is BigBasket's category mix?
    query = """
    SELECT category,COUNT(product_id) AS product_count,
    ROUND(COUNT(product_id)*100.0/NULLIF((SELECT COUNT(*) FROM products),0),2) AS category_mix_percent
    FROM products GROUP BY category ORDER BY product_count DESC
    """
    kpi_4_result = fetch_data(
        query,
        [],
    )

    # KPI 5: How many price outliers are there?
    query = """
    SELECT COUNT(*) AS price_outlier_count FROM products
    WHERE selling_price > (SELECT AVG(selling_price)*2 FROM products)
       OR selling_price < (SELECT AVG(selling_price)*0.5 FROM products)
    """
    kpi_5_result = fetch_data(
        query,
        [],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Product Count",
            "Average Selling Price",
            "Average Discount %",
            "Category Mix",
            "Outlier Count",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which categories dominate BigBasket's catalogue?
    show_question(1, "Which categories dominate BigBasket's catalogue?")

    query = """
    SELECT category,COUNT(product_id) AS product_count FROM products
    GROUP BY category ORDER BY product_count DESC
    """
    question_1_result = fetch_data(
        query,
        [],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "category",
        "product_count",
        "Which categories dominate BigBasket's catalogue?",
        horizontal=True,
    )

    # Question 2: Which products have the highest discounts?
    show_question(2, "Which products have the highest discounts?")

    query = """
    SELECT product_id,product_name,category,ROUND(discount_percent,2) AS discount_percent,
    ROUND(mrp,2) AS mrp,ROUND(selling_price,2) AS selling_price
    FROM products ORDER BY discount_percent DESC LIMIT 20
    """
    question_2_result = fetch_data(
        query,
        [],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_2_result,
        "product_name",
        "discount_percent",
        "Which products have the highest discounts?",
        horizontal=True,
    )

    # Question 3: Which products have unusually high prices?
    show_question(3, "Which products have unusually high prices?")

    query = """
    SELECT product_id,product_name,category,ROUND(selling_price,2) AS selling_price,
    ROUND(selling_price/(SELECT AVG(selling_price) FROM products),2) AS price_vs_average
    FROM products WHERE selling_price > (SELECT AVG(selling_price)*2 FROM products)
    ORDER BY selling_price DESC
    """
    question_3_result = fetch_data(
        query,
        [],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_3_result,
        "product_name",
        "selling_price",
        "Which products have unusually high prices?",
        horizontal=True,
    )

def render_bigbasket_customer():

    # ========================================================
    # 5. BIGBASKET — CUSTOMER
    # ========================================================

    show_section_header(
        "BigBasket — Customer",
        "Customer base, acquisition, geography, signup and app mix.",
    )

    # --------------------------------------------------------
    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: Total Customers
    query = """
    SELECT
        COUNT(DISTINCT c.customer_id) AS total_customers
    FROM customers c
    WHERE (LOWER(TRIM(c.signup_platform)) LIKE 'big basket%' OR LOWER(TRIM(c.signup_platform)) = 'bigbasket')
    """
    kpi_1_result = fetch_data(
        query,
        [],
    )

    # KPI 2: Active Customers
    # Customers from the platform signup base who have
    # placed at least one order on the selected platform.
    query = """
    SELECT
        COUNT(DISTINCT o.customer_id) AS active_customers
    FROM orders o
    INNER JOIN customers c
        ON o.customer_id = c.customer_id
    WHERE o.platform_id = ?
      AND (LOWER(TRIM(c.signup_platform)) LIKE 'big basket%' OR LOWER(TRIM(c.signup_platform)) = 'bigbasket')
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: Customer Activation Rate
    # Active Customers / Total Customers * 100
    query = """
    WITH platform_customers AS (
        SELECT DISTINCT
            c.customer_id
        FROM customers c
        WHERE (LOWER(TRIM(c.signup_platform)) LIKE 'big basket%' OR LOWER(TRIM(c.signup_platform)) = 'bigbasket')
    ),
    active_customers AS (
        SELECT DISTINCT
            o.customer_id
        FROM orders o
        INNER JOIN platform_customers pc
            ON o.customer_id = pc.customer_id
        WHERE o.platform_id = ?
    )
    SELECT
        ROUND(
            COUNT(DISTINCT ac.customer_id) * 100.0
            / NULLIF(
                COUNT(DISTINCT pc.customer_id),
                0
            ),
            2
        ) AS activation_rate_percent
    FROM platform_customers pc
    LEFT JOIN active_customers ac
        ON pc.customer_id = ac.customer_id
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: Orders per Customer
    # Total platform orders / Active Customers
    query = """
    WITH platform_customers AS (
        SELECT DISTINCT
            c.customer_id
        FROM customers c
        WHERE (LOWER(TRIM(c.signup_platform)) LIKE 'big basket%' OR LOWER(TRIM(c.signup_platform)) = 'bigbasket')
    ),
    active_customers AS (
        SELECT DISTINCT
            o.customer_id
        FROM orders o
        INNER JOIN platform_customers pc
            ON o.customer_id = pc.customer_id
        WHERE o.platform_id = ?
    ),
    platform_orders AS (
        SELECT
            COUNT(DISTINCT o.order_id) AS total_orders
        FROM orders o
        INNER JOIN platform_customers pc
            ON o.customer_id = pc.customer_id
        WHERE o.platform_id = ?
    )
    SELECT
        ROUND(
            po.total_orders * 1.0
            / NULLIF(
                COUNT(DISTINCT ac.customer_id),
                0
            ),
            2
        ) AS orders_per_customer
    FROM active_customers ac
    CROSS JOIN platform_orders po
    """
    kpi_4_result = fetch_data(
        query,
        [
            selected_platform_id,
            selected_platform_id,
        ],
    )

    # KPI 5: Repeat Customer Rate
    # Customers with more than one order / Active Customers * 100
    query = """
    WITH platform_customers AS (
        SELECT DISTINCT
            c.customer_id
        FROM customers c
        WHERE (LOWER(TRIM(c.signup_platform)) LIKE 'big basket%' OR LOWER(TRIM(c.signup_platform)) = 'bigbasket')
    ),
    customer_order_counts AS (
        SELECT
            o.customer_id,
            COUNT(DISTINCT o.order_id) AS order_count
        FROM orders o
        INNER JOIN platform_customers pc
            ON o.customer_id = pc.customer_id
        WHERE o.platform_id = ?
        GROUP BY o.customer_id
    )
    SELECT
        ROUND(
            SUM(
                CASE
                    WHEN order_count > 1
                    THEN 1
                    ELSE 0
                END
            ) * 100.0
            / NULLIF(
                COUNT(customer_id),
                0
            ),
            2
        ) AS repeat_customer_rate_percent
    FROM customer_order_counts
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Total Customers",
            "Active Customers",
            "Customer Activation Rate",
            "Orders per Customer",
            "Repeat Customer Rate",
        ],
    )

    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which cities have the largest BigBasket customer base?
    show_question(1, "Which cities have the largest BigBasket customer base?")

    query = """
    SELECT city,COUNT(customer_id) AS customers FROM customers
    WHERE LOWER(TRIM(signup_platform)) LIKE 'big basket%' OR LOWER(TRIM(signup_platform)) = 'bigbasket' GROUP BY city ORDER BY customers DESC
    """
    question_1_result = fetch_data(
        query,
        [],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "city",
        "customer_count",
        "Which cities have the largest BigBasket customer base?",
        horizontal=True,
    )

    # Question 2: Which cities are growing fastest?
    show_question(2, "Which cities are growing fastest?")

    query = """
    WITH city_month AS (
        SELECT
            city,
            strftime('%Y-%m', signup_date) AS month,
            COUNT(customer_id) AS new_customers
        FROM customers
        WHERE (
            LOWER(TRIM(signup_platform)) LIKE 'big basket%'
            OR LOWER(TRIM(signup_platform)) = 'bigbasket'
        )
          AND signup_date IS NOT NULL
        GROUP BY city, strftime('%Y-%m', signup_date)
    ),
    city_bounds AS (
        SELECT
            city,
            MIN(month) AS first_month,
            MAX(month) AS last_month
        FROM city_month
        GROUP BY city
    )
    SELECT
        cm.city,
        MAX(CASE WHEN cm.month = cb.first_month THEN cm.new_customers END) AS first_month_customers,
        MAX(CASE WHEN cm.month = cb.last_month THEN cm.new_customers END) AS last_month_customers,
        ROUND(
            (
                MAX(CASE WHEN cm.month = cb.last_month THEN cm.new_customers END)
                - MAX(CASE WHEN cm.month = cb.first_month THEN cm.new_customers END)
            ) * 100.0
            / NULLIF(MAX(CASE WHEN cm.month = cb.first_month THEN cm.new_customers END), 0),
            2
        ) AS growth_percent
    FROM city_month cm
    JOIN city_bounds cb
        ON cm.city = cb.city
    GROUP BY cm.city
    ORDER BY growth_percent DESC
    """
    question_2_result = fetch_data(
        query,
        [],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: HORIZONTAL BAR CHART
    # Direct growth rate makes the fastest-growing cities easy to compare.
    draw_bar_chart(
        question_2_result,
        "city",
        "growth_percent",
        "Which Cities Are Growing Fastest?",
        horizontal=True,
    )

    # Question 3: Where is customer acquisition weak?
    show_question(3, "Where is customer acquisition weak?")

    query = """
    SELECT city,COUNT(customer_id) AS customers FROM customers
    WHERE LOWER(TRIM(signup_platform)) LIKE 'big basket%' OR LOWER(TRIM(signup_platform)) = 'bigbasket' GROUP BY city ORDER BY customers ASC
    """
    question_3_result = fetch_data(
        query,
        [],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_3_result,
        "city",
        "customers",
        "Where is Customer Acquisition Weak?",
        horizontal=True,
    )

def render_bigbasket_orders():

    # ========================================================
    # 6. BIGBASKET — ORDERS
    # ========================================================

    show_section_header(
        "BigBasket — Orders",
        "Order volume, AOV, completion, cancellations, returns and payment behavior.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: What is BigBasket's total number of orders?
    query = """
    SELECT COUNT(order_id) AS total_orders FROM orders WHERE platform_id=?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: What is BigBasket's AOV?
    query = """
    SELECT ROUND(AVG(order_value_inr),2) AS aov_inr FROM orders WHERE platform_id=?
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: What is BigBasket's delivery completion rate?
    query = """
    SELECT ROUND(SUM(CASE WHEN LOWER(TRIM(order_status))='delivered' THEN 1 ELSE 0 END)*100.0/NULLIF(COUNT(order_id),0),2) AS delivery_completion_rate_percent
    FROM orders WHERE platform_id=?
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: What is BigBasket's cancellation rate?
    query = """
    SELECT ROUND(SUM(CASE WHEN LOWER(TRIM(order_status))='cancelled' THEN 1 ELSE 0 END)*100.0/NULLIF(COUNT(order_id),0),2) AS cancellation_rate_percent
    FROM orders WHERE platform_id=?
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: What is BigBasket's return rate?
    query = """
    SELECT ROUND(SUM(CASE WHEN LOWER(TRIM(order_status))='returned' THEN 1 ELSE 0 END)*100.0/NULLIF(COUNT(order_id),0),2) AS return_rate_percent
    FROM orders WHERE platform_id=?
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Total Orders",
            "AOV",
            "Delivery Completion Rate",
            "Cancellation Rate",
            "Return Rate",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which cities generate the highest number of BigBasket orders?
    show_question(1, "Which cities generate the highest number of BigBasket orders?")

    query = """
    SELECT ds.city,COUNT(o.order_id) AS total_orders,ROUND(AVG(o.order_value_inr),2) AS aov
    FROM orders o JOIN dark_stores ds ON o.store_id=ds.store_id WHERE o.platform_id=? GROUP BY ds.city ORDER BY total_orders DESC
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "city",
        "total_orders",
        "Which cities generate the highest number of BigBasket orders?",
        horizontal=True,
    )

    # Question 2: Which cities have high cancellation rates?
    show_question(2, "Which cities have high cancellation rates?")

    query = """
    SELECT ds.city,COUNT(o.order_id) AS orders,
    ROUND(SUM(CASE WHEN LOWER(TRIM(o.order_status))='cancelled' THEN 1 ELSE 0 END)*100.0/COUNT(o.order_id),2) AS cancellation_rate_percent
    FROM orders o JOIN dark_stores ds ON o.store_id=ds.store_id WHERE o.platform_id=? GROUP BY ds.city ORDER BY cancellation_rate_percent DESC
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_2_result,
        "city",
        "cancellation_rate_percent",
        "Which cities have high cancellation rates?",
        horizontal=True,
    )

    # Question 3: Which stores generate the most orders?
    show_question(3, "Which stores generate the most orders?")

    query = """
    SELECT o.store_id,ds.store_name,ds.city,COUNT(o.order_id) AS total_orders
    FROM orders o LEFT JOIN dark_stores ds ON o.store_id=ds.store_id
    WHERE o.platform_id=? GROUP BY o.store_id,ds.store_name,ds.city ORDER BY total_orders DESC
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_3_result,
        "store_name",
        "total_orders",
        "Which stores generate the most orders?",
        horizontal=True,
    )

def render_bigbasket_order_items():

    # ========================================================
    # 7. BIGBASKET — ORDER ITEMS
    # ========================================================

    show_section_header(
        "BigBasket — Order Items",
        "Product demand, basket composition, item value and basket growth.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: How many units has BigBasket sold?
    query = """
    SELECT SUM(oi.quantity) AS units_sold FROM order_items oi JOIN orders o ON oi.order_id=o.order_id WHERE o.platform_id=?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: What is BigBasket's total item value?
    query = """
    SELECT ROUND(SUM(oi.line_total_inr),2) AS item_value FROM order_items oi JOIN orders o ON oi.order_id=o.order_id WHERE o.platform_id=?
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: What is BigBasket's average item price?
    query = """
    SELECT ROUND(AVG(oi.item_price_inr),2) AS average_item_price FROM order_items oi JOIN orders o ON oi.order_id=o.order_id WHERE o.platform_id=?
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: What is BigBasket's average basket size?
    query = """
    SELECT ROUND(SUM(oi.quantity)*1.0/NULLIF(COUNT(DISTINCT oi.order_id),0),2) AS average_basket_size_units
    FROM order_items oi JOIN orders o ON oi.order_id=o.order_id WHERE o.platform_id=?
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: What is category contribution to BigBasket item value?
    query = """
    SELECT p.category,ROUND(SUM(oi.line_total_inr),2) AS item_value,
    ROUND(SUM(oi.line_total_inr)*100.0/NULLIF((SELECT SUM(oi2.line_total_inr) FROM order_items oi2 JOIN orders o2 ON oi2.order_id=o2.order_id WHERE o2.platform_id=?),0),2) AS contribution_percent
    FROM order_items oi JOIN orders o ON oi.order_id=o.order_id JOIN products p ON oi.product_id=p.product_id
    WHERE o.platform_id=? GROUP BY p.category ORDER BY item_value DESC
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id] * 2,
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Units Sold",
            "Item Value",
            "Average Item Price",
            "Average Basket Size",
            "Category Contribution",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which products sell the highest quantities?
    show_question(1, "Which products sell the highest quantities?")

    query = """
    SELECT p.product_id,p.product_name,p.category,SUM(oi.quantity) AS units_sold
    FROM order_items oi JOIN products p ON oi.product_id=p.product_id JOIN orders o ON oi.order_id=o.order_id
    WHERE o.platform_id=? GROUP BY p.product_id,p.product_name,p.category ORDER BY units_sold DESC LIMIT 20
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "product_name",
        "units_sold",
        "Which products sell the highest quantities?",
        horizontal=True,
    )

    # Question 2: Which products generate the most value?
    show_question(2, "Which products generate the most value?")

    query = """
    SELECT p.product_id,p.product_name,p.category,ROUND(SUM(oi.line_total_inr),2) AS item_value
    FROM order_items oi JOIN products p ON oi.product_id=p.product_id JOIN orders o ON oi.order_id=o.order_id
    WHERE o.platform_id=? GROUP BY p.product_id,p.product_name,p.category ORDER BY item_value DESC LIMIT 20
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_2_result,
        "product_name",
        "item_value",
        "Which products generate the most value?",
        horizontal=True,
    )

    # Question 3: Which categories dominate BigBasket baskets?
    show_question(3, "Which categories dominate BigBasket baskets?")

    query = """
    SELECT p.category,SUM(oi.quantity) AS units_sold,ROUND(SUM(oi.line_total_inr),2) AS item_value
    FROM order_items oi JOIN products p ON oi.product_id=p.product_id JOIN orders o ON oi.order_id=o.order_id
    WHERE o.platform_id=? GROUP BY p.category ORDER BY item_value DESC,units_sold DESC
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: DONUT / PIE CHART
    draw_pie_chart(
        question_3_result,
        "category",
        "item_value",
        "Which categories dominate BigBasket baskets?",
    )

def render_bigbasket_inventory():

    # ========================================================
    # 8. BIGBASKET — INVENTORY
    # ========================================================

    show_section_header(
        "BigBasket — Inventory",
        "Stock levels, reorder risk, expiry risk, overstock and working capital.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: How many stock units does BigBasket hold?
    query = """
    SELECT SUM(stock_units) AS total_stock_units FROM inventory
    WHERE store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: How many low-stock SKUs does BigBasket have?
    query = """
    SELECT COUNT(*) AS low_stock_sku_count FROM inventory
    WHERE stock_units<reorder_level AND store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: What is BigBasket's reorder risk?
    query = """
    SELECT ROUND(SUM(CASE WHEN stock_units<reorder_level THEN 1 ELSE 0 END)*100.0/NULLIF(COUNT(*),0),2) AS reorder_risk_percent
    FROM inventory WHERE store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: What is BigBasket's expiry risk?
    query = """
    SELECT COUNT(*) AS expiry_risk_count FROM inventory
    WHERE expiry_date IS NOT NULL AND date(expiry_date)<=date('now','+30 day')
    AND store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: How concentrated is BigBasket inventory?
    query = """
    SELECT store_id,SUM(stock_units) AS stock_units,
    ROUND(SUM(stock_units)*100.0/NULLIF((SELECT SUM(stock_units) FROM inventory WHERE store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=?)),0),2) AS inventory_share_percent
    FROM inventory WHERE store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
    GROUP BY store_id ORDER BY inventory_share_percent DESC
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id] * 2,
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Stock Units",
            "Low-stock SKU Count",
            "Reorder Risk",
            "Expiry Risk",
            "Inventory Concentration",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which stores have the highest stockout risk?
    show_question(1, "Which stores have the highest stockout risk?")

    query = """
    SELECT i.store_id,ds.store_name,ds.city,COUNT(*) AS sku_count,
    SUM(CASE WHEN i.stock_units<i.reorder_level THEN 1 ELSE 0 END) AS low_stock_skus
    FROM inventory i JOIN dark_stores ds ON i.store_id=ds.store_id
    WHERE i.store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
    GROUP BY i.store_id,ds.store_name,ds.city ORDER BY low_stock_skus DESC
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "store_name",
        "low_stock_skus",
        "Which stores have the highest stockout risk?",
        horizontal=True,
    top_n=8,
)

    # Question 2: Which products are below reorder level?
    show_question(2, "Which products are below reorder level?")

    query = """
    SELECT i.product_id,p.product_name,p.category,i.store_id,i.stock_units,i.reorder_level
    FROM inventory i JOIN products p ON i.product_id=p.product_id
    WHERE i.stock_units<i.reorder_level AND i.store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
    ORDER BY (i.reorder_level-i.stock_units) DESC
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: GROUPED BAR CHART
    draw_metric_comparison(
        question_2_result,
        "product_name",
        ["stock_units", "reorder_level"],
        "Which products are below reorder level?",
    )

    # Question 3: Which stores are overstocked?
    show_question(3, "Which stores are overstocked?")

    query = """
    SELECT i.store_id,ds.store_name,ds.city,SUM(i.stock_units) AS stock_units,SUM(i.reorder_level) AS reorder_units,
    ROUND(SUM(i.stock_units)*1.0/NULLIF(SUM(i.reorder_level),0),2) AS stock_to_reorder_ratio
    FROM inventory i JOIN dark_stores ds ON i.store_id=ds.store_id
    WHERE i.store_id IN (SELECT DISTINCT store_id FROM orders WHERE platform_id=? )
    GROUP BY i.store_id,ds.store_name,ds.city HAVING stock_to_reorder_ratio>2
    ORDER BY stock_to_reorder_ratio DESC
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_metric_comparison(
        question_3_result,
        "store_id",
        ["stock_units", "reorder_units"],
        "Actual Stock vs Reorder Units — Overstocked Stores",
    )

def render_bigbasket_logistics():

    # ========================================================
    # 9. BIGBASKET — LOGISTICS
    # ========================================================

    show_section_header(
        "BigBasket — Logistics",
        "Delays, distance, ratings, vehicle performance and delivery optimization.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: What is BigBasket's delay rate?
    query = """
    SELECT ROUND(SUM(CASE WHEN LOWER(TRIM(l.delay_flag))='yes' THEN 1 ELSE 0 END)*100.0/NULLIF(COUNT(l.delivery_id),0),2) AS delay_rate_percent
    FROM logistics l JOIN orders o ON l.order_id=o.order_id WHERE o.platform_id=?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: What is BigBasket's average delivery distance?
    query = """
    SELECT ROUND(AVG(l.distance_km),2) AS average_delivery_distance_km
    FROM logistics l JOIN orders o ON l.order_id=o.order_id WHERE o.platform_id=?
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: What is BigBasket's average delivery rating?
    query = """
    SELECT ROUND(AVG(l.delivery_rating),2) AS average_delivery_rating
    FROM logistics l JOIN orders o ON l.order_id=o.order_id WHERE o.platform_id=?
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: How many BigBasket deliveries were delayed?
    query = """
    SELECT COUNT(l.delivery_id) AS delayed_deliveries FROM logistics l JOIN orders o ON l.order_id=o.order_id
    WHERE o.platform_id=? AND LOWER(TRIM(l.delay_flag))='yes'
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: What is BigBasket's vehicle mix?
    query = """
    SELECT l.vehicle_type,COUNT(l.delivery_id) AS deliveries,
    ROUND(COUNT(l.delivery_id)*100.0/NULLIF((SELECT COUNT(l2.delivery_id) FROM logistics l2 JOIN orders o2 ON l2.order_id=o2.order_id WHERE o2.platform_id=?),0),2) AS vehicle_share_percent
    FROM logistics l JOIN orders o ON l.order_id=o.order_id WHERE o.platform_id=?
    GROUP BY l.vehicle_type ORDER BY deliveries DESC
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id] * 2,
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Delay Rate",
            "Average Delivery Distance",
            "Average Delivery Rating",
            "Delayed Deliveries",
            "Vehicle Mix",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which cities have the highest delays?
    show_question(1, "Which cities have the highest delays?")

    query = """
    SELECT ds.city,COUNT(l.delivery_id) AS deliveries,
    ROUND(SUM(CASE WHEN LOWER(TRIM(l.delay_flag))='yes' THEN 1 ELSE 0 END)*100.0/NULLIF(COUNT(l.delivery_id),0),2) AS delay_rate_percent
    FROM logistics l JOIN orders o ON l.order_id=o.order_id JOIN dark_stores ds ON o.store_id=ds.store_id WHERE o.platform_id=?
    GROUP BY ds.city ORDER BY delay_rate_percent DESC
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "city",
        "delay_rate_percent",
        "Which cities have the highest delays?",
        horizontal=True,
    )

    # Question 2: Which vehicle types perform best?
    show_question(2, "Which vehicle types perform best?")

    query = """
    SELECT l.vehicle_type,COUNT(l.delivery_id) AS deliveries,
    ROUND(SUM(CASE WHEN LOWER(TRIM(l.delay_flag))='yes' THEN 1 ELSE 0 END)*100.0/NULLIF(COUNT(l.delivery_id),0),2) AS delay_rate_percent,
    ROUND(AVG(l.delivery_rating),2) AS average_rating
    FROM logistics l JOIN orders o ON l.order_id=o.order_id WHERE o.platform_id=?
    GROUP BY l.vehicle_type ORDER BY delay_rate_percent ASC,average_rating DESC
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_2_result,
        "vehicle_type",
        "delay_rate_percent",
        "Which vehicle types perform best?",
        horizontal=True,
    )

    # Question 3: Does distance influence delay?
    show_question(3, "Does distance influence delay?")

    query = """
    SELECT CASE WHEN distance_km<2 THEN '0-2 km' WHEN distance_km<5 THEN '2-5 km' WHEN distance_km<10 THEN '5-10 km' ELSE '10+ km' END AS distance_band,
    COUNT(l.delivery_id) AS deliveries,
    ROUND(SUM(CASE WHEN LOWER(TRIM(l.delay_flag))='yes' THEN 1 ELSE 0 END)*100.0/NULLIF(COUNT(l.delivery_id),0),2) AS delay_rate_percent
    FROM logistics l JOIN orders o ON l.order_id=o.order_id WHERE o.platform_id=?
    GROUP BY distance_band ORDER BY MIN(distance_km)
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_3_result,
        "distance_band",
        "delay_rate_percent",
        "Does distance influence delay?",
        horizontal=False,
    )

    # Question 4: Which cities receive poor ratings?
    show_question(4, "Which cities receive poor ratings?")

    query = """
    SELECT ds.city,COUNT(l.delivery_id) AS deliveries,ROUND(AVG(l.delivery_rating),2) AS average_rating
    FROM logistics l JOIN orders o ON l.order_id=o.order_id JOIN dark_stores ds ON o.store_id=ds.store_id WHERE o.platform_id=?
    GROUP BY ds.city ORDER BY average_rating ASC
    """
    question_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_4_result = apply_dashboard_filters(
        question_4_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_4_result,
        "city",
        "average_rating",
        "Which cities receive poor ratings?",
        horizontal=True,
    )

    # Question 5: Where should BigBasket optimize delivery operations?
    show_question(5, "Where should BigBasket optimize delivery operations?")

    query = """
    SELECT ds.city,l.vehicle_type,COUNT(l.delivery_id) AS deliveries,
    ROUND(SUM(CASE WHEN LOWER(TRIM(l.delay_flag))='yes' THEN 1 ELSE 0 END)*100.0/NULLIF(COUNT(l.delivery_id),0),2) AS delay_rate_percent,
    ROUND(AVG(l.delivery_rating),2) AS average_rating
    FROM logistics l JOIN orders o ON l.order_id=o.order_id JOIN dark_stores ds ON o.store_id=ds.store_id WHERE o.platform_id=?
    GROUP BY ds.city,l.vehicle_type ORDER BY delay_rate_percent DESC,average_rating ASC
    """
    question_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_5_result = apply_dashboard_filters(
        question_5_result
    )

    # CHART TYPE: BAR CHART FOR CITY + VEHICLE COMBINATIONS
    logistics_chart = question_5_result.copy()

    if (
        not logistics_chart.empty
        and "city" in logistics_chart.columns
        and "vehicle_type" in logistics_chart.columns
    ):
        logistics_chart["city_vehicle"] = (
            logistics_chart["city"].astype(str)
            + " — "
            + logistics_chart["vehicle_type"].astype(str)
        )
    elif not logistics_chart.empty:
        logistics_chart["city_vehicle"] = (
            logistics_chart.index.astype(str)
        )

    draw_bar_chart(
        logistics_chart,
        "city_vehicle",
        "delay_rate_percent",
        "Where should BigBasket optimize delivery operations?",
        horizontal=True,
    )


def render_bigbasket_monthly_p_l():

    # ========================================================
    # 10. BIGBASKET — MONTHLY P&L
    # ========================================================

    show_section_header(
        "BigBasket — Monthly P&L",
        "Revenue, COGS, operating costs, profit and monthly margin trends.",
    )

    # --------------------------------------------------------
    # FIVE KPI QUERIES
    # --------------------------------------------------------

    # KPI 1: What is BigBasket's total P&L revenue?
    query = """
    SELECT ROUND(SUM(revenue_inr),2) AS revenue FROM pnl_monthly_safe WHERE platform_id=?
    """
    kpi_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 2: What is BigBasket's total COGS?
    query = """
    SELECT ROUND(SUM(cogs_inr),2) AS cogs FROM pnl_monthly_safe WHERE platform_id=?
    """
    kpi_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 3: What is BigBasket's total operating expense?
    query = """
    SELECT ROUND(SUM(delivery_cost_inr)+SUM(marketing_spend_inr)+SUM(employee_cost_inr)+SUM(other_opex_inr),2) AS operating_expense
    FROM pnl_monthly_safe WHERE platform_id=?
    """
    kpi_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 4: What is BigBasket's total profit?
    query = """
    SELECT ROUND(SUM(profit_inr),2) AS profit FROM pnl_monthly_safe WHERE platform_id=?
    """
    kpi_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    # KPI 5: What is BigBasket's profit margin?
    query = """
    SELECT ROUND(SUM(profit_inr)*100.0/NULLIF(SUM(revenue_inr),0),2) AS profit_margin_percent
    FROM pnl_monthly_safe WHERE platform_id=?
    """
    kpi_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    show_kpi_cards(
        [
            kpi_1_result,
            kpi_2_result,
            kpi_3_result,
            kpi_4_result,
            kpi_5_result,
        ],
        [
            "Revenue",
            "COGS",
            "Operating Expense",
            "Profit",
            "Profit Margin",
        ],
    )

    # --------------------------------------------------------
    # FIVE BUSINESS-QUESTION CHARTS
    # --------------------------------------------------------

    # Question 1: Which cities generate the most revenue?
    show_question(1, "Which cities generate the most revenue?")

    query = """
    SELECT city,ROUND(SUM(revenue_inr),2) AS revenue FROM pnl_monthly_safe
    WHERE platform_id=? GROUP BY city ORDER BY revenue DESC
    """
    question_1_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_1_result = apply_dashboard_filters(
        question_1_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_1_result,
        "city",
        "revenue",
        "Which cities generate the most revenue?",
        horizontal=True,
    )

    # Question 2: Which cities produce the highest profit margins?
    show_question(2, "Which cities produce the highest profit margins?")

    query = """
    SELECT city,ROUND(SUM(revenue_inr),2) AS revenue,ROUND(SUM(profit_inr),2) AS profit,
    ROUND(SUM(profit_inr)*100.0/NULLIF(SUM(revenue_inr),0),2) AS profit_margin_percent
    FROM pnl_monthly_safe WHERE platform_id=? GROUP BY city ORDER BY profit_margin_percent DESC
    """
    question_2_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_2_result = apply_dashboard_filters(
        question_2_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_2_result,
        "city",
        "profit_margin_percent",
        "Which cities produce the highest profit margins?",
        horizontal=True,
    )

    # Question 3: Which cities are loss-making?
    show_question(3, "Which cities are loss-making?")

    query = """
    SELECT city,ROUND(SUM(revenue_inr),2) AS revenue,ROUND(SUM(profit_inr),2) AS profit,
    ROUND(SUM(profit_inr)*100.0/NULLIF(SUM(revenue_inr),0),2) AS profit_margin_percent
    FROM pnl_monthly_safe WHERE platform_id=? GROUP BY city HAVING profit<0 ORDER BY profit ASC
    """
    question_3_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_3_result = apply_dashboard_filters(
        question_3_result
    )

    # CHART TYPE: BAR CHART
    draw_bar_chart(
        question_3_result,
        "city",
        "profit",
        "Which cities are loss-making?",
        horizontal=True,
    )

    # Question 4: Which costs hurt profitability most?
    show_question(4, "Which costs hurt profitability most?")

    query = """
    SELECT ROUND(SUM(cogs_inr),2) AS cogs,ROUND(SUM(delivery_cost_inr),2) AS delivery_cost,
    ROUND(SUM(marketing_spend_inr),2) AS marketing_spend,ROUND(SUM(employee_cost_inr),2) AS employee_cost,
    ROUND(SUM(other_opex_inr),2) AS other_opex
    FROM pnl_monthly_safe WHERE platform_id=?
    """
    question_4_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_4_result = apply_dashboard_filters(
        question_4_result
    )

    # CHART TYPE: BAR CHART FOR COST CATEGORIES
    draw_cost_chart(
        question_4_result,
        "Which costs hurt profitability most?",
    )

    # Question 5: How is monthly profit changing?
    show_question(5, "How is monthly profit changing?")

    query = """
    SELECT month,ROUND(SUM(revenue_inr),2) AS revenue,ROUND(SUM(profit_inr),2) AS profit,
    ROUND(SUM(profit_inr)*100.0/NULLIF(SUM(revenue_inr),0),2) AS profit_margin_percent
    FROM pnl_monthly_safe WHERE platform_id=? GROUP BY month ORDER BY month
    """
    question_5_result = fetch_data(
        query,
        [selected_platform_id],
    )

    question_5_result = apply_dashboard_filters(
        question_5_result
    )

    # CHART TYPE: LINE CHART
    color_column = None

    draw_line_chart(
        question_5_result,
        "month",
        "profit",
        "How is monthly profit changing?",
        color_column=color_column,
    )


# ============================================================
# STEP 16: FINAL DASHBOARD DISPATCH
# ============================================================

show_hero()

_RENDERERS = {
    ("Zepto", "Overview"): render_zepto_overview,
    ("Zepto", "Store"): render_zepto_store,
    ("Zepto", "Employee"): render_zepto_employee,
    ("Zepto", "Product"): render_zepto_product,
    ("Zepto", "Customer"): render_zepto_customer,
    ("Zepto", "Orders"): render_zepto_orders,
    ("Zepto", "Order Items"): render_zepto_order_items,
    ("Zepto", "Inventory"): render_zepto_inventory,
    ("Zepto", "Logistics"): render_zepto_logistics,
    ("Zepto", "Monthly P&L"): render_zepto_monthly_p_l,
    ("Blinkit", "Overview"): render_blinkit_overview,
    ("Blinkit", "Store"): render_blinkit_store,
    ("Blinkit", "Employee"): render_blinkit_employee,
    ("Blinkit", "Product"): render_blinkit_product,
    ("Blinkit", "Customer"): render_blinkit_customer,
    ("Blinkit", "Orders"): render_blinkit_orders,
    ("Blinkit", "Order Items"): render_blinkit_order_items,
    ("Blinkit", "Inventory"): render_blinkit_inventory,
    ("Blinkit", "Logistics"): render_blinkit_logistics,
    ("Blinkit", "Monthly P&L"): render_blinkit_monthly_p_l,
    ("Swiggy Instamart", "Overview"): render_swiggy_instamart_overview,
    ("Swiggy Instamart", "Store"): render_swiggy_instamart_store,
    ("Swiggy Instamart", "Employee"): render_swiggy_instamart_employee,
    ("Swiggy Instamart", "Product"): render_swiggy_instamart_product,
    ("Swiggy Instamart", "Customer"): render_swiggy_instamart_customer,
    ("Swiggy Instamart", "Orders"): render_swiggy_instamart_orders,
    ("Swiggy Instamart", "Order Items"): render_swiggy_instamart_order_items,
    ("Swiggy Instamart", "Inventory"): render_swiggy_instamart_inventory,
    ("Swiggy Instamart", "Logistics"): render_swiggy_instamart_logistics,
    ("Swiggy Instamart", "Monthly P&L"): render_swiggy_instamart_monthly_p_l,
    ("BigBasket", "Overview"): render_bigbasket_overview,
    ("BigBasket", "Store"): render_bigbasket_store,
    ("BigBasket", "Employee"): render_bigbasket_employee,
    ("BigBasket", "Product"): render_bigbasket_product,
    ("BigBasket", "Customer"): render_bigbasket_customer,
    ("BigBasket", "Orders"): render_bigbasket_orders,
    ("BigBasket", "Order Items"): render_bigbasket_order_items,
    ("BigBasket", "Inventory"): render_bigbasket_inventory,
    ("BigBasket", "Logistics"): render_bigbasket_logistics,
    ("BigBasket", "Monthly P&L"): render_bigbasket_monthly_p_l,
}

renderer = _RENDERERS.get(
    (selected_platform, selected_section)
)

if renderer is None:
    st.error(
        f"No dashboard renderer is available for "        f"{selected_platform} — {selected_section}."
    )
else:
    try:
        renderer()
    except Exception as error:
        st.error("The selected dashboard section could not be rendered."        )
        st.exception(error)
