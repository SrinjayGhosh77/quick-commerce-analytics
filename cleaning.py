import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
import os


cleaned_folder = "cleaned data"
os.makedirs(cleaned_folder, exist_ok=True)


# Load the platform dataset

Platforms = pd.read_csv('01_platforms.csv')
print(Platforms)

Platforms.to_csv(
    os.path.join(cleaned_folder, "01_platforms_cleaned.csv"),
    index=False
)

#STORE DATA CLEANING

# Load the dark store dataset
store = pd.read_csv("02_dark_stores.csv")

print(store)

# Check missing values
print(store.isnull().sum())

# Check duplicate rows and unique
print(store.duplicated().sum())

print(store.nunique().sort_values(ascending=False))

# Convert opened_date to datetime
store["opened_date"] = pd.to_datetime(
    store["opened_date"],
    format="mixed",
    errors="coerce"
)

# Standardize city names
city_mapping = {
    "bengaluru": "Bengaluru",
    "bangalore": "Bengaluru",
    "blr": "Bengaluru",
    "mumbai": "Mumbai",
    "bombay": "Mumbai",
    "delhi": "Delhi",
    "new delhi": "Delhi"
}

store["city_clean"] = (
    store["city"]
    .str.strip()
    .str.capitalize()
    .replace(city_mapping)
)

# Remove store numbers from store names
store["clean_store_name"] = (
    store["store_name"]
    .str.replace(r"\s+\d+$", "", regex=True)
    .str.strip()
)

# Clean pincode
store["pincode"] = pd.to_numeric(
    store["pincode"],
    errors="coerce"
)

store["pincode"] = (
    store["pincode"]
    .astype("Int64")
    .astype("string")
)

# Keep only 6-digit pincodes
valid_pincode = store["pincode"].str.fullmatch(r"\d{6}")

# Replace invalid and missing pincodes with Unknown
store.loc[
    ~valid_pincode.fillna(False),
    "pincode"
] = "Unknown"

def pincode_status(row):

    if pd.isna(row["pincode"]):
        return "Missing"

    if not str(row["pincode"]).isdigit():
        return "Invalid"

    if len(str(row["pincode"])) != 6:
        return "Invalid"

    return "Valid"


store["pincode_status"] = store.apply(
    pincode_status,
    axis=1
)


# Fill missing sqft using platform + city median
store["sqft_area"] = (
    store.groupby(
        ["platform_id", "city"]
    )["sqft_area"]
    .transform(lambda x: x.fillna(x.median()))
)

# Fill remaining missing sqft using platform median
store["sqft_area"] = (
    store["sqft_area"]
    .fillna(
        store.groupby("platform_id")["sqft_area"]
        .transform("median")
    )
)

# Display final cleaned data
print(store.head())

#st.dataframe(store)

store.to_csv(
    os.path.join(cleaned_folder, "02_dark_stores_cleaned.csv"),
    index=False
)


#EMPLOYEE DATA CLEANING

employee= pd.read_csv('03_employees.csv')

print(employee)

print(employee.info())

print(employee.isnull().sum())

print(employee.duplicated().sum())

print(employee.nunique().sort_values(ascending=False))


# STEP 2 — REMOVE EXACT DUPLICATES
# ============================================================
# Remove completely identical employee records.

employee = employee.drop_duplicates().copy()


# ============================================================
# STEP 3 — CLEAN EMPLOYEE ID
# ============================================================
# Convert employee_id into numeric format.

employee["employee_id"] = pd.to_numeric(
    employee["employee_id"],
    errors="coerce"
).astype("Int64")


# ============================================================
# STEP 4 — CLEAN STORE ID
# ============================================================
# Convert store_id into numeric format first.

employee["store_id"] = pd.to_numeric(
    employee["store_id"],
    errors="coerce"
).astype("Int64")


# ============================================================
# STEP 5 — CREATE CLEAN STORE ID
# ============================================================
# Valid store IDs are between 6001 and 6150.
#
# If an ID is outside this range, map it into the valid
# 6001–6150 range using a deterministic calculation.
#
# The original store_id is preserved.

def clean_store_id(store_id):

    if pd.isna(store_id):
        return pd.NA

    if 6001 <= store_id <= 6150:
        return int(store_id)

    return 6001 + ((int(store_id) - 7000) % 150)


employee["clean_store_id"] = (
    employee["store_id"]
    .apply(clean_store_id)
    .astype("Int64")
)


# ============================================================
# STEP 6 — CLEAN EMPLOYEE NAME
# ============================================================
# Remove unnecessary spaces from employee names.

employee["employee_name"] = (
    employee["employee_name"]
    .astype("string")
    .str.strip()
)


# ============================================================
# STEP 7 — STANDARDIZE ROLE
# ============================================================
# Convert different role formats into a consistent format.
#
# Example:
# PICKER → Picker
# delivery rider → Delivery Rider

employee["role"] = (
    employee["role"]
    .astype("string")
    .str.strip()
    .str.lower()
    .str.title()
)


# ============================================================
# STEP 8 — STANDARDIZE GENDER
# ============================================================
# Standardize M/m/Male and F/f/Female.
# Missing values are labelled as Unknown.

employee["gender"] = (
    employee["gender"]
    .astype("string")
    .str.strip()
    .str.lower()
)

gender_mapping = {
    "m": "Male",
    "male": "Male",
    "f": "Female",
    "female": "Female"
}

employee["gender"] = (
    employee["gender"]
    .replace(gender_mapping)
    .fillna("Unknown")
)


# ============================================================
# STEP 9 — CLEAN SALARY
# ============================================================
# Convert salary into numeric format.

employee["monthly_salary_inr"] = pd.to_numeric(
    employee["monthly_salary_inr"],
    errors="coerce"
)


# ============================================================
# STEP 10 — FILL MISSING SALARY
# ============================================================
# Missing salary is filled using the median salary
# of the employee's role.

role_median_salary = (
    employee
    .groupby("role")["monthly_salary_inr"]
    .transform("median")
)

employee["monthly_salary_inr"] = (
    employee["monthly_salary_inr"]
    .fillna(role_median_salary)
)


# ============================================================
# STEP 11 — IDENTIFY SALARY OUTLIERS
# ============================================================
# Detect salary outliers using the IQR method.
#
# Instead of True/False, we write:
# Outlier
# Normal

Q1 = employee["monthly_salary_inr"].quantile(0.25)
Q3 = employee["monthly_salary_inr"].quantile(0.75)

IQR = Q3 - Q1

lower_bound = Q1 - (1.5 * IQR)
upper_bound = Q3 + (1.5 * IQR)

employee["salary_status"] = np.where(
    (
        (employee["monthly_salary_inr"] < lower_bound)
        |
        (employee["monthly_salary_inr"] > upper_bound)
    ),
    "Outlier",
    "Normal"
)


# ============================================================
# STEP 12 — CLEAN JOINING DATE
# ============================================================
# Convert mixed date formats into datetime.

employee["joining_date"] = pd.to_datetime(
    employee["joining_date"],
    format="mixed",
    errors="coerce"
)

# ============================================================
# STEP 1 — CLEAN EMPLOYMENT STATUS
# ============================================================
# Standardize employment status before creating work status.

employee["employment_status"] = (
    employee["employment_status"]
    .astype("string")
    .str.strip()
    .str.lower()
    .replace({
        "active": "Active",
        "resigned": "Resigned",
        "on leave": "On Leave"
    })
)


# ============================================================
# STEP 2 — MAKE SURE JOINING DATE IS DATETIME
# ============================================================

employee["joining_date"] = pd.to_datetime(
    employee["joining_date"],
    format="mixed",
    errors="coerce"
)


# ============================================================
# STEP 3 — USE TODAY AS REFERENCE DATE
# ============================================================
# Do not use joining_date.max().

REFERENCE_DATE = pd.Timestamp.today().normalize()


# ============================================================
# CREATE WORK STATUS
# ============================================================

REFERENCE_DATE = pd.Timestamp.today().normalize()


def get_work_status(row):

    # Resigned employees remain Resigned
    if row["employment_status"] == "Resigned":
        return "Resigned"

    # Employees on leave remain On Leave
    if row["employment_status"] == "On Leave":
        return "On Leave"

    # Active employee with a future joining date
    if (
        row["employment_status"] == "Active"
        and pd.notna(row["joining_date"])
        and row["joining_date"] > REFERENCE_DATE
    ):
        return "Joining in Future"

    # Active employee who has already joined
    if row["employment_status"] == "Active":
        return "Currently Working"

    return "Unknown"


employee["work_status"] = employee.apply(
    get_work_status,
    axis=1
)

# ============================================================
# STEP 15 — FINAL DATA CHECK
# ============================================================
# Check whether important columns still contain missing values.

print(employee.isnull().sum())

print(employee["salary_status"].value_counts())

print(employee["work_status"].value_counts())


# ============================================================
# STEP 16 — DISPLAY CLEAN DATA
# ============================================================

#st.dataframe(employee)

employee.to_csv(
    os.path.join(cleaned_folder, "03_employees_cleaned.csv"),
    index=False
)

#PRODUCT DATA CLEANING

products = pd.read_csv('04_products.csv')

print(products)

# Check dataset structure, missing values and duplicates.

print(products.info())
print(products.isnull().sum())
print("Exact duplicates:", products.duplicated().sum())


# ============================================================
# STEP 3 — REMOVE EXACT DUPLICATES
# ============================================================
# Remove completely identical records.

products = products.drop_duplicates().copy()


# ============================================================
# STEP 4 — CLEAN PRODUCT ID
# ============================================================
# Convert product_id into integer format.

products["product_id"] = pd.to_numeric(
    products["product_id"],
    errors="coerce"
).astype("Int64")


# Check product ID uniqueness.

print("Unique product IDs:", products["product_id"].nunique())
print(
    "Duplicate product IDs:",
    products["product_id"].duplicated().sum()
)


# ============================================================
# STEP 5 — CLEAN PRODUCT NAME
# ============================================================
# Remove unnecessary spaces.
# Product names are not duplicated automatically because
# different products can have the same name.

products["product_name"] = (
    products["product_name"]
    .astype("string")
    .str.strip()
)


# ============================================================
# STEP 6 — STANDARDIZE CATEGORY
# ============================================================
# Clean category formatting and keep standard category names.

products["category"] = (
    products["category"]
    .astype("string")
    .str.strip()
    .str.title()
)


# ============================================================
# STEP 7 — CLEAN BRAND
# ============================================================
# Remove unnecessary spaces.
# Missing brands are replaced with Unknown.
# We do not guess missing brands.

products["brand"] = (
    products["brand"]
    .astype("string")
    .str.strip()
    .replace("", pd.NA)
    .fillna("Unknown")
)


# ============================================================
# STEP 8 — STANDARDIZE UNIT
# ============================================================
# Standardize different representations of the same unit.
#
# kg / Kg  → Kg
# pc / PC  → PC
# l / L    → L

unit_mapping = {
    "kg": "Kg",
    "Kg": "Kg",
    "g": "g",
    "ml": "ml",
    "l": "L",
    "L": "L",
    "pc": "PC",
    "PC": "PC"
}

products["unit"] = (
    products["unit"]
    .astype("string")
    .str.strip()
    .replace(unit_mapping)
)


# ============================================================
# STEP 9 — CLEAN PRICE COLUMNS
# ============================================================
# Convert MRP and selling price into numeric format.

products["mrp"] = pd.to_numeric(
    products["mrp"],
    errors="coerce"
)

products["selling_price"] = pd.to_numeric(
    products["selling_price"],
    errors="coerce"
)


# ============================================================
# STEP 10 — CHECK INVALID PRICES
# ============================================================
# Prices should not be zero or negative.

products.loc[
    products["mrp"] <= 0,
    "mrp"
] = np.nan

products.loc[
    products["selling_price"] <= 0,
    "selling_price"
] = np.nan


# ============================================================
# STEP 11 — CALCULATE CATEGORY DISCOUNT RATE
# ============================================================
# Use records where both MRP and selling price are available.
#
# Discount rate:
#
# (MRP - Selling Price) / MRP

complete_price = (
    products["mrp"].notna()
    &
    products["selling_price"].notna()
    &
    (products["mrp"] > 0)
)

products["discount_rate_temp"] = np.nan

products.loc[
    complete_price,
    "discount_rate_temp"
] = (
    (
        products.loc[complete_price, "mrp"]
        -
        products.loc[complete_price, "selling_price"]
    )
    /
    products.loc[complete_price, "mrp"]
)


# ============================================================
# STEP 12 — CATEGORY LEVEL DISCOUNT RATE
# ============================================================
# Calculate median discount for each category.

category_discount = (
    products.groupby("category")["discount_rate_temp"]
    .transform("median")
)

# Overall median discount as fallback.

overall_discount = (
    products["discount_rate_temp"]
    .median()
)

category_discount = (
    category_discount
    .fillna(overall_discount)
)


# ============================================================
# STEP 13 — FILL MISSING MRP
# ============================================================
# Case 1:
# MRP is missing but selling price is available.
#
# Estimated MRP =
# Selling Price / (1 - Category Discount)

mrp_missing = products["mrp"].isna()
selling_available = products["selling_price"].notna()

products.loc[
    mrp_missing & selling_available,
    "mrp"
] = (
    products.loc[
        mrp_missing & selling_available,
        "selling_price"
    ]
    /
    (
        1 -
        category_discount[
            mrp_missing & selling_available
        ]
    )
)


# ============================================================
# STEP 14 — FILL MISSING SELLING PRICE
# ============================================================
# Case 2:
# Selling price is missing but MRP is available.
#
# Estimated Selling Price =
# MRP × (1 - Category Discount)

selling_missing = products["selling_price"].isna()
mrp_available = products["mrp"].notna()

products.loc[
    selling_missing & mrp_available,
    "selling_price"
] = (
    products.loc[
        selling_missing & mrp_available,
        "mrp"
    ]
    *
    (
        1 -
        category_discount[
            selling_missing & mrp_available
        ]
    )
)


# ============================================================
# STEP 15 — HANDLE BOTH MRP AND SELLING PRICE MISSING
# ============================================================
# If both prices are missing, use category median MRP first.
# Then calculate selling price using category discount.

category_mrp = (
    products.groupby("category")["mrp"]
    .transform("median")
)

both_missing = (
    products["mrp"].isna()
    &
    products["selling_price"].isna()
)

products.loc[
    both_missing,
    "mrp"
] = category_mrp[both_missing]


products.loc[
    both_missing,
    "selling_price"
] = (
    products.loc[
        both_missing,
        "mrp"
    ]
    *
    (
        1 -
        category_discount[both_missing]
    )
)


# ============================================================
# STEP 16 — FINAL PRICE FALLBACK
# ============================================================
# Make sure no price remains missing.
# Category median is used as final fallback.

products["mrp"] = (
    products["mrp"]
    .fillna(
        products.groupby("category")["mrp"]
        .transform("median")
    )
)

products["selling_price"] = (
    products["selling_price"]
    .fillna(
        products.groupby("category")["selling_price"]
        .transform("median")
    )
)


# ============================================================
# STEP 17 — ENSURE SELLING PRICE <= MRP
# ============================================================
# Business rule:
#
# Selling price should not be greater than MRP.
#
# If this situation occurs after imputation, cap the
# selling price at MRP.

products["selling_price"] = np.minimum(
    products["selling_price"],
    products["mrp"]
)


# ============================================================
# STEP 18 — ROUND PRICE VALUES
# ============================================================
# Keep prices at two decimal places.

products["mrp"] = products["mrp"].round(2)

products["selling_price"] = (
    products["selling_price"]
    .round(2)
)


# ============================================================
# STEP 19 — CALCULATE DISCOUNT PERCENTAGE
# ============================================================
# Calculate final product discount.

products["discount_percent"] = (
    (
        products["mrp"]
        -
        products["selling_price"]
    )
    /
    products["mrp"]
    * 100
).round(2)


# ============================================================
# STEP 20 — IDENTIFY PRICE OUTLIERS
# ============================================================
# Use IQR method to identify unusual MRP values.
#
# We do not delete outliers.
# We label them as Normal or Outlier.

Q1 = products["mrp"].quantile(0.25)

Q3 = products["mrp"].quantile(0.75)

IQR = Q3 - Q1

lower_bound = Q1 - (1.5 * IQR)

upper_bound = Q3 + (1.5 * IQR)


products["price_status"] = np.where(
    (
        (products["mrp"] < lower_bound)
        |
        (products["mrp"] > upper_bound)
    ),
    "Outlier",
    "Normal"
)


# ============================================================
# STEP 21 — REMOVE TEMPORARY COLUMN
# ============================================================
# Remove the temporary discount calculation column.

products = products.drop(
    columns=["discount_rate_temp"]
)


# ============================================================
# STEP 22 — FINAL DATA TYPE CHECK
# ============================================================
# Make sure important columns have proper data types.

products["product_id"] = (
    products["product_id"]
    .astype("Int64")
)

products["product_name"] = (
    products["product_name"]
    .astype("string")
)

products["category"] = (
    products["category"]
    .astype("string")
)

products["brand"] = (
    products["brand"]
    .astype("string")
)

products["unit"] = (
    products["unit"]
    .astype("string")
)


# ============================================================
# STEP 23 — FINAL DATA QUALITY CHECK
# ============================================================
# Check whether any important data quality problems remain.

print("Rows:", len(products))

print("Columns:", len(products.columns))

print(
    "Duplicate rows:",
    products.duplicated().sum()
)

print(
    "Duplicate product IDs:",
    products["product_id"].duplicated().sum()
)

print(
    "Missing product IDs:",
    products["product_id"].isna().sum()
)

print(
    "Missing product names:",
    products["product_name"].isna().sum()
)

print(
    "Missing categories:",
    products["category"].isna().sum()
)

print(
    "Missing brands:",
    products["brand"].isna().sum()
)

print(
    "Missing units:",
    products["unit"].isna().sum()
)

print(
    "Missing MRP:",
    products["mrp"].isna().sum()
)

print(
    "Missing selling price:",
    products["selling_price"].isna().sum()
)

print(
    "Selling price > MRP:",
    (products["selling_price"] > products["mrp"]).sum()
)


# ============================================================
# STEP 24 — CHECK PRICE STATUS
# ============================================================

print(
    products["price_status"].value_counts()
)


# ============================================================
# STEP 25 — CHECK UNIT VALUES
# ============================================================

print(
    products["unit"].value_counts()
)


# ============================================================
# STEP 26 — SAVE CLEANED DATA
# ============================================================
# Save the final cleaned dataset for analysis and dashboard use.

products.to_csv(
    "04_products_cleaned.csv",
    index=False
)

#st.dataframe(products)


products.to_csv(
    os.path.join(cleaned_folder, "04_products_cleaned.csv"),
    index=False
)

#CUSTOMER DATA CLEANING

#Load data

df= pd.read_csv('05_customers.csv')

# i have dropped columns phone and email as it is mere customer private info
# and has no contribution whatsoever in data analysis

df = df.drop(columns=["phone","email"])


# trimming and transforming customer names to title case

df["customer_name"] = df["customer_name"].str.strip().str.title()

# trimming and transforming app_version names to lower case and replacing blanks with others because
# there can be other platforms like linux

df["app_version"] = df["app_version"].str.strip().str.lower().replace({
    "android" : "Android",
    "ios" : "IOS"
})

df["app_version"] = df["app_version"].fillna("Others")

# changing Bangalore/Bengaluru/BLR to Bengaluru and Bombay to Mumbai because both are the same

df["city"] = df["city"].str.strip().str.title().replace({
    "Mumbai": "Mumbai",
    "Bombay": "Mumbai"
})

df["city"] = df["city"].str.strip().str.title().replace({
    "Bangalore": "Bengaluru",
    "Bengaluru": "Bengaluru",
    "Blr": "Bengaluru"
})

# cleaning platform names

df["signup_platform"] = df["signup_platform"].str.strip().str.title().replace({
    "Bigbasket": "Big Basket"
})

# cleaning signup dates

df["signup_date"] = pd.to_datetime(
    df["signup_date"],
    errors="coerce",
    format="mixed"
).dt.strftime("%d-%m-%Y")

#st.dataframe(df)

df.to_csv(
    os.path.join(cleaned_folder, "05_customers_cleaned.csv"),
    index=False
)

# ============================================================
# ORDERS + ORDER ITEMS DATA CLEANING
# ============================================================

# Load orders
order = pd.read_csv("06_orders.csv")

# Load order items
order_items = pd.read_csv("07_order_items.csv")


# ============================================================
# STEP 1 — CLEAN BASIC DATA TYPES
# ============================================================

order["order_id"] = pd.to_numeric(
    order["order_id"],
    errors="coerce"
).astype("Int64")

order["order_value_inr"] = pd.to_numeric(
    order["order_value_inr"],
    errors="coerce"
)

order["discount_inr"] = pd.to_numeric(
    order["discount_inr"],
    errors="coerce"
).fillna(0)


order_items["order_id"] = pd.to_numeric(
    order_items["order_id"],
    errors="coerce"
).astype("Int64")

order_items["product_id"] = pd.to_numeric(
    order_items["product_id"],
    errors="coerce"
).astype("Int64")

order_items["quantity"] = pd.to_numeric(
    order_items["quantity"],
    errors="coerce"
)

order_items["item_price_inr"] = pd.to_numeric(
    order_items["item_price_inr"],
    errors="coerce"
)


# ============================================================
# STEP 2 — CLEAN QUANTITY
# ============================================================

order_items["quantity"] = order_items["quantity"].abs()

order_items.loc[
    order_items["quantity"] == 0,
    "quantity"
] = np.nan


# ============================================================
# STEP 3 — CLEAN ORDER DATE
# ============================================================

order["order_datetime"] = pd.to_datetime(
    order["order_datetime"],
    format="mixed",
    errors="coerce"
)


# ============================================================
# STEP 4 — CLEAN DELIVERY TIME
# ============================================================

order["actual_delivery_min"] = (
    order["actual_delivery_min"]
    .fillna(order["promised_delivery_min"])
)


# ============================================================
# STEP 5 — CLEAN ORDER STATUS
# ============================================================

order["order_status"] = (
    order["order_status"]
    .astype("string")
    .str.strip()
    .str.title()
)


# ============================================================
# STEP 6 — CLEAN PAYMENT MODE
# ============================================================

order["payment_mode"] = (
    order["payment_mode"]
    .astype("string")
    .str.strip()
    .str.lower()
    .replace({
        "upi": "Upi",
        "cod": "Cod",
        "wallet": "Wallet",
        "card": "Card"
    })
)


# ============================================================
# STEP 7 — CALCULATE KNOWN LINE TOTALS
# ============================================================
# Only rows with available item price are used here.

order_items["line_total_inr"] = (
    order_items["quantity"]
    *
    order_items["item_price_inr"]
)


known_items = order_items[
    order_items["item_price_inr"].notna()
    &
    order_items["quantity"].notna()
].copy()


known_order_total = (
    known_items
    .groupby("order_id")["line_total_inr"]
    .sum()
    .rename("known_item_total")
)


# ============================================================
# STEP 8 — CHECK ORDER VALUE BUSINESS LOGIC
# ============================================================
# Test two possibilities:
#
# 1. Order Value = Gross item total
# 2. Order Value = Gross item total - Discount


reconciliation = order.merge(
    known_order_total,
    on="order_id",
    how="left"
)


reconciliation["gross_difference"] = (
    reconciliation["known_item_total"]
    -
    reconciliation["order_value_inr"]
).abs()


reconciliation["net_difference"] = (
    reconciliation["known_item_total"]
    -
    (
        reconciliation["order_value_inr"]
        +
        reconciliation["discount_inr"]
    )
).abs()


gross_error = reconciliation[
    "gross_difference"
].median()

net_error = reconciliation[
    "net_difference"
].median()


if pd.isna(gross_error):
    gross_error = np.inf

if pd.isna(net_error):
    net_error = np.inf


if net_error < gross_error:
    order_value_model = "net"
else:
    order_value_model = "gross"


print("Order value model:", order_value_model)


# ============================================================
# STEP 9 — CREATE TARGET GROSS VALUE
# ============================================================

if order_value_model == "net":

    order["target_gross_value"] = (
        order["order_value_inr"]
        +
        order["discount_inr"]
    )

else:

    order["target_gross_value"] = (
        order["order_value_inr"]
    )


# ============================================================
# STEP 10 — GET HISTORICAL PRODUCT PRICE
# ============================================================

product_historical_price = (
    order_items
    .groupby("product_id")["item_price_inr"]
    .median()
)


# ============================================================
# STEP 11 — GET PRODUCT SELLING PRICE
# ============================================================

product_reference = products[
    [
        "product_id",
        "selling_price",
        "category"
    ]
].drop_duplicates("product_id")


order_items = order_items.merge(
    product_reference,
    on="product_id",
    how="left"
)


# ============================================================
# STEP 12 — CREATE REFERENCE PRICE
# ============================================================
# Priority:
# Historical item price
#        ↓
# Product selling price
#        ↓
# Category median


order_items["historical_price"] = (
    order_items["product_id"]
    .map(product_historical_price)
)


order_items["reference_price"] = (
    order_items["historical_price"]
    .fillna(order_items["selling_price"])
)


category_reference_price = (
    order_items
    .groupby("category")["reference_price"]
    .transform("median")
)


order_items["reference_price"] = (
    order_items["reference_price"]
    .fillna(category_reference_price)
)


# Final fallback
order_items["reference_price"] = (
    order_items["reference_price"]
    .fillna(
        order_items["reference_price"].median()
    )
)


# ============================================================
# STEP 13 — FILL MISSING ITEM PRICES
# ============================================================
# Use order-level reconciliation where possible.


for order_id, group in order_items.groupby("order_id"):

    target = order.loc[
        order["order_id"] == order_id,
        "target_gross_value"
    ]

    if target.empty or pd.isna(target.iloc[0]):
        continue

    target = target.iloc[0]

    missing_mask = group["item_price_inr"].isna()

    if not missing_mask.any():
        continue

    known_total = (
        group.loc[
            ~missing_mask,
            "quantity"
        ]
        *
        group.loc[
            ~missing_mask,
            "item_price_inr"
        ]
    ).sum()

    remaining_value = target - known_total

    missing_rows = group.loc[
        missing_mask
    ].copy()


    # --------------------------------------------------------
    # ONE MISSING ITEM PRICE
    # --------------------------------------------------------

    if len(missing_rows) == 1:

        idx = missing_rows.index[0]

        quantity = order_items.loc[
            idx,
            "quantity"
        ]

        if (
            pd.notna(quantity)
            and quantity > 0
            and remaining_value > 0
        ):

            inferred_price = (
                remaining_value / quantity
            )

            order_items.loc[
                idx,
                "item_price_inr"
            ] = inferred_price


    # --------------------------------------------------------
    # MULTIPLE MISSING ITEM PRICES
    # --------------------------------------------------------

    else:

        if remaining_value > 0:

            missing_rows["reference_line_value"] = (
                missing_rows["quantity"]
                *
                missing_rows["reference_price"]
            )

            total_reference_value = (
                missing_rows[
                    "reference_line_value"
                ].sum()
            )

            if total_reference_value > 0:

                for idx, row in missing_rows.iterrows():

                    allocated_value = (
                        remaining_value
                        *
                        row["reference_line_value"]
                        /
                        total_reference_value
                    )

                    if (
                        pd.notna(row["quantity"])
                        and row["quantity"] > 0
                    ):

                        inferred_price = (
                            allocated_value
                            /
                            row["quantity"]
                        )

                        order_items.loc[
                            idx,
                            "item_price_inr"
                        ] = inferred_price


# ============================================================
# STEP 14 — FINAL FALLBACK FOR ITEM PRICE
# ============================================================

order_items["item_price_inr"] = (
    order_items["item_price_inr"]
    .fillna(order_items["historical_price"])
)

order_items["item_price_inr"] = (
    order_items["item_price_inr"]
    .fillna(order_items["selling_price"])
)

order_items["item_price_inr"] = (
    order_items["item_price_inr"]
    .fillna(order_items["reference_price"])
)


# ============================================================
# STEP 15 — FINAL LINE TOTAL
# ============================================================

order_items["line_total_inr"] = (
    order_items["quantity"]
    *
    order_items["item_price_inr"]
)


# ============================================================
# STEP 16 — CALCULATE ORDER TOTAL FROM ORDER ITEMS
# ============================================================

calculated_order_total = (
    order_items
    .groupby("order_id")["line_total_inr"]
    .sum()
)


# ============================================================
# STEP 17 — FILL MISSING ORDER VALUE
# ============================================================

order["calculated_gross_value"] = (
    order["order_id"]
    .map(calculated_order_total)
)


if order_value_model == "net":

    order["calculated_order_value"] = (
        order["calculated_gross_value"]
        -
        order["discount_inr"]
    )

else:

    order["calculated_order_value"] = (
        order["calculated_gross_value"]
    )


order["order_value_inr"] = (
    order["order_value_inr"]
    .fillna(
        order["calculated_order_value"]
    )
)


# ============================================================
# STEP 18 — FINAL RECONCILIATION
# ============================================================

final_order_total = (
    order_items
    .groupby("order_id")["line_total_inr"]
    .sum()
    .rename("calculated_total")
    .reset_index()
)


final_check = final_order_total.merge(
    order[
        [
            "order_id",
            "order_value_inr",
            "discount_inr"
        ]
    ],
    on="order_id",
    how="left"
)


if order_value_model == "net":

    final_check["difference"] = (
        final_check["calculated_total"]
        -
        (
            final_check["order_value_inr"]
            +
            final_check["discount_inr"]
        )
    )

else:

    final_check["difference"] = (
        final_check["calculated_total"]
        -
        final_check["order_value_inr"]
    )


print(
    "Remaining missing item prices:",
    order_items["item_price_inr"].isna().sum()
)

print(
    "Remaining missing order values:",
    order["order_value_inr"].isna().sum()
)

print(
    "Maximum reconciliation difference:",
    final_check["difference"].abs().max()
)


# ============================================================
# STEP 19 — CLEAN TEMPORARY COLUMNS
# ============================================================

order_items = order_items.drop(
    columns=[
        "selling_price",
        "category",
        "historical_price",
        "reference_price"
    ],
    errors="ignore"
)

order = order.drop(
    columns=[
        "target_gross_value",
        "calculated_gross_value",
        "calculated_order_value"
    ],
    errors="ignore"
)


# ============================================================
# STEP 20 — ROUND VALUES
# ============================================================

order_items["item_price_inr"] = (
    order_items["item_price_inr"]
    .round(2)
)

order_items["line_total_inr"] = (
    order_items["line_total_inr"]
    .round(2)
)

order["order_value_inr"] = (
    order["order_value_inr"]
    .round(2)
)


# ============================================================
# STEP 21 — SAVE CLEANED FILES
# ============================================================

order.to_csv(
    os.path.join(
        cleaned_folder,
        "06_orders_cleaned.csv"
    ),
    index=False
)


order_items.to_csv(
    os.path.join(
        cleaned_folder,
        "07_order_items_cleaned.csv"
    ),
    index=False
)

# st.dataframe(order_items)
# st.dataframe(order)

#INVENTORY DATA CLEANNING

# STEP 1 — LOAD DATA
# ============================================================
# Load the raw inventory dataset.

inventory = pd.read_csv("08_inventory.csv")


# ============================================================
# STEP 2 — CHECK RAW DATA
# ============================================================
# Check data types, missing values and duplicate rows.

print(inventory.info())
print(inventory.isnull().sum())
print("Duplicate rows:", inventory.duplicated().sum())


# ============================================================
# STEP 3 — REMOVE EXACT DUPLICATES
# ============================================================
# Remove completely identical rows.

inventory = inventory.drop_duplicates().copy()


# ============================================================
# STEP 4 — CLEAN STOCK UNITS
# ============================================================
# Missing stock units are treated as zero.

inventory["stock_units"] = (
    inventory["stock_units"]
    .fillna(0)
)


# ============================================================
# STEP 5 — CLEAN REORDER LEVEL
# ============================================================
# Missing reorder levels are filled using the overall mean.

inventory["reorder_level"] = (
    inventory["reorder_level"]
    .fillna(
        inventory["reorder_level"].mean()
    )
)


# ============================================================
# STEP 6 — CLEAN LAST RESTOCK DATE
# ============================================================
# Convert mixed date formats into datetime.

inventory["last_restock_date"] = pd.to_datetime(
    inventory["last_restock_date"],
    format="mixed",
    errors="coerce"
)


# Check missing restock dates

print(
    "Missing last restock dates:",
    inventory["last_restock_date"].isna().sum()
)


# ============================================================
# STEP 7 — CLEAN EXPIRY DATE
# ============================================================
# Convert expiry_date into datetime.

inventory["expiry_date"] = pd.to_datetime(
    inventory["expiry_date"],
    format="mixed",
    errors="coerce"
)


# ============================================================
# STEP 8 — FILL MISSING EXPIRY DATES
# ============================================================
# If expiry date is missing, use one day after the
# last restock date.

inventory["expiry_date"] = (
    inventory["expiry_date"]
    .fillna(
        inventory["last_restock_date"]
        + pd.Timedelta(days=1)
    )
)


# ============================================================
# STEP 9 — FORMAT DATES
# ============================================================
# Convert dates into YYYY-MM-DD format for the final CSV.

inventory["last_restock_date"] = (
    inventory["last_restock_date"]
    .dt.strftime("%Y-%m-%d")
)

inventory["expiry_date"] = (
    inventory["expiry_date"]
    .dt.strftime("%Y-%m-%d")
)


# ============================================================
# STEP 10 — FINAL DATA CHECK
# ============================================================

print(inventory.isnull().sum())
print("Duplicate rows:", inventory.duplicated().sum())


# ============================================================
# STEP 11 — CREATE CLEANED DATA FOLDER
# ============================================================

cleaned_folder = "cleaned data"

os.makedirs(
    cleaned_folder,
    exist_ok=True
)


# ============================================================
# STEP 12 — SAVE CLEANED DATA
# ============================================================

inventory.to_csv(
    os.path.join(
        cleaned_folder,
        "08_inventory_cleaned.csv"
    ),
    index=False
)

#st.dataframe(inventory)


#LOGISTIC DATA CLEANING

# ============================================================
# STEP 1 — LOAD DATA
# ============================================================

logistics = pd.read_csv("09_logistics_delivery.csv")


# ============================================================
# STEP 2 — CHECK RAW DATA
# ============================================================

print(logistics.info())
print(logistics.isnull().sum())
print("Duplicate rows:", logistics.duplicated().sum())


# ============================================================
# STEP 3 — REMOVE EXACT DUPLICATES
# ============================================================

logistics = logistics.drop_duplicates().copy()


# ============================================================
# STEP 4 — CLEAN DELAY FLAG
# ============================================================
# Standardize delay flag values.
#
# Y → Yes
# N → No

logistics["delay_flag"] = (
    logistics["delay_flag"]
    .astype("string")
    .str.strip()
    .str.upper()
    .replace({
        "Y": "Yes",
        "N": "No"
    })
)


# ============================================================
# STEP 5 — CLEAN VEHICLE TYPE
# ============================================================
# Standardize vehicle names.

logistics["vehicle_type"] = (
    logistics["vehicle_type"]
    .astype("string")
    .str.strip()
    .str.lower()
)

vehicle_mapping = {
    "bike": "Bike",
    "bicycle": "Bicycle",
    "ev": "EV",
    "ev scooter": "EV Scooter"
}

logistics["vehicle_type"] = (
    logistics["vehicle_type"]
    .replace(vehicle_mapping)
)


# ============================================================
# STEP 6 — CLEAN DISTANCE
# ============================================================
# Convert distance into numeric format.

logistics["distance_km"] = pd.to_numeric(
    logistics["distance_km"],
    errors="coerce"
)


# ============================================================
# STEP 7 — CHECK DISTANCE BY VEHICLE TYPE
# ============================================================
# Analyze distance before filling missing values.

vehicle_analysis = (
    logistics
    .groupby("vehicle_type")["distance_km"]
    .agg(
        count="count",
        mean="mean",
        median="median",
        max="max"
    )
    .round(2)
)

print("Distance analysis:")
print(vehicle_analysis)


# ============================================================
# STEP 8 — FILL MISSING DISTANCE
# ============================================================
# Use vehicle-wise median distance.

logistics["distance_km"] = (
    logistics
    .groupby("vehicle_type")["distance_km"]
    .transform(
        lambda x: x.fillna(x.median())
    )
)


# ============================================================
# STEP 9 — CLEAN DELIVERY RATING
# ============================================================
# Convert rating into numeric format.

logistics["delivery_rating"] = pd.to_numeric(
    logistics["delivery_rating"],
    errors="coerce"
)


# ============================================================
# STEP 10 — CHECK RATING BY DELAY STATUS
# ============================================================
# Analyze rating before filling missing values.

delay_rating = (
    logistics
    .groupby("delay_flag")["delivery_rating"]
    .agg(
        count="count",
        mean="mean",
        median="median"
    )
    .round(2)
)

print("Delay-wise rating:")
print(delay_rating)


# ============================================================
# STEP 11 — FILL MISSING DELIVERY RATING
# ============================================================
# Use delay-wise median rating.

logistics["delivery_rating"] = (
    logistics
    .groupby("delay_flag")["delivery_rating"]
    .transform(
        lambda x: x.fillna(x.median())
    )
)


# ============================================================
# STEP 12 — FINAL CHECK
# ============================================================

print("Remaining distance nulls:",
      logistics["distance_km"].isnull().sum())

print("Remaining rating nulls:",
      logistics["delivery_rating"].isnull().sum())

print("Duplicate rows:",
      logistics.duplicated().sum())


# ============================================================
# STEP 13 — CREATE CLEANED DATA FOLDER
# ============================================================

cleaned_folder = "cleaned data"

os.makedirs(
    cleaned_folder,
    exist_ok=True
)


# ============================================================
# STEP 14 — SAVE CLEANED DATA
# ============================================================

logistics.to_csv(
    os.path.join(
        cleaned_folder,
        "09_logistics_delivery_cleaned.csv"
    ),
    index=False
)

#st.dataframe(logistics)


# ============================================================
# PNL MONTHLY DATA CLEANING
# ============================================================


# ============================================================
# STEP 1 — LOAD DATA
# ============================================================

pnl = pd.read_csv("10_pnl_monthly.csv")


# ============================================================
# STEP 2 — INITIAL DATA CHECK
# ============================================================
# Check structure, missing values and duplicate rows.

print(pnl.info())

print("\nMissing values before cleaning:")
print(pnl.isnull().sum())

print(
    "\nExact duplicate rows:",
    pnl.duplicated().sum()
)


# ============================================================
# STEP 3 — REMOVE EXACT DUPLICATES
# ============================================================
# Remove completely identical records.

pnl = pnl.drop_duplicates().copy()


# ============================================================
# STEP 4 — CHECK PRIMARY KEY
# ============================================================
# pnl_id should be unique.

print(
    "\nDuplicate pnl_id:",
    pnl["pnl_id"].duplicated().sum()
)


# ============================================================
# STEP 5 — CLEAN PLATFORM ID
# ============================================================

pnl["platform_id"] = pd.to_numeric(
    pnl["platform_id"],
    errors="coerce"
).astype("Int64")


# ============================================================
# STEP 6 — CLEAN CITY
# ============================================================
# Standardize city names such as:
# mumbai → Mumbai
# bengaluru → Bengaluru

pnl["city"] = (
    pnl["city"]
    .astype("string")
    .str.strip()
    .str.title()
)

city_mapping = {
    "Bangalore": "Bengaluru",
    "Bengaluru": "Bengaluru",
    "Blr": "Bengaluru",
    "Bombay": "Mumbai",
    "Mumbai": "Mumbai"
}

pnl["city"] = (
    pnl["city"]
    .replace(city_mapping)
)


# ============================================================
# STEP 7 — CLEAN MONTH
# ============================================================
# Convert month into proper datetime format.

pnl["month"] = pd.to_datetime(
    pnl["month"],
    format="%Y-%m",
    errors="coerce"
)


# ============================================================
# STEP 8 — CLEAN NUMERIC COLUMNS
# ============================================================

numeric_columns = [
    "revenue_inr",
    "cogs_inr",
    "delivery_cost_inr",
    "marketing_spend_inr",
    "employee_cost_inr",
    "other_opex_inr",
    "orders_count"
]

for col in numeric_columns:

    pnl[col] = pd.to_numeric(
        pnl[col],
        errors="coerce"
    )


# ============================================================
# STEP 9 — HANDLE INVALID NEGATIVE VALUES
# ============================================================
# Financial amounts and order count should not be negative
# in this dataset.

for col in numeric_columns:

    pnl.loc[
        pnl[col] < 0,
        col
    ] = np.nan


# ============================================================
# STEP 10 — FILL MISSING REVENUE
# ============================================================
# Business logic:
#
# Revenue is strongly related to COGS in this dataset.
# So calculate platform-level Revenue / COGS ratio.
#
# Missing Revenue =
# COGS × Platform Median Revenue/COGS Ratio


valid_revenue_ratio = (
    pnl["revenue_inr"].notna()
    &
    pnl["cogs_inr"].notna()
    &
    (pnl["cogs_inr"] > 0)
)


pnl["revenue_cogs_ratio_temp"] = np.nan


pnl.loc[
    valid_revenue_ratio,
    "revenue_cogs_ratio_temp"
] = (
    pnl.loc[
        valid_revenue_ratio,
        "revenue_inr"
    ]
    /
    pnl.loc[
        valid_revenue_ratio,
        "cogs_inr"
    ]
)


platform_revenue_ratio = (
    pnl.groupby("platform_id")
    ["revenue_cogs_ratio_temp"]
    .transform("median")
)


overall_revenue_ratio = (
    pnl["revenue_cogs_ratio_temp"]
    .median()
)


platform_revenue_ratio = (
    platform_revenue_ratio
    .fillna(overall_revenue_ratio)
)


missing_revenue = (
    pnl["revenue_inr"].isna()
    &
    pnl["cogs_inr"].notna()
    &
    (pnl["cogs_inr"] > 0)
)


pnl.loc[
    missing_revenue,
    "revenue_inr"
] = (
    pnl.loc[
        missing_revenue,
        "cogs_inr"
    ]
    *
    platform_revenue_ratio[
        missing_revenue
    ]
)


# ============================================================
# STEP 11 — FILL MISSING COST VALUES
# ============================================================
# Business logic:
#
# Each cost is calculated as a proportion of Revenue.
#
# Missing Cost =
# Revenue × Platform Median Cost/Revenue Ratio


cost_columns = [
    "cogs_inr",
    "delivery_cost_inr",
    "marketing_spend_inr",
    "employee_cost_inr",
    "other_opex_inr"
]


for col in cost_columns:

    valid_cost_ratio = (
        pnl["revenue_inr"].notna()
        &
        pnl[col].notna()
        &
        (pnl["revenue_inr"] > 0)
    )


    pnl[f"{col}_ratio_temp"] = np.nan


    pnl.loc[
        valid_cost_ratio,
        f"{col}_ratio_temp"
    ] = (
        pnl.loc[
            valid_cost_ratio,
            col
        ]
        /
        pnl.loc[
            valid_cost_ratio,
            "revenue_inr"
        ]
    )


    platform_cost_ratio = (
        pnl.groupby("platform_id")
        [f"{col}_ratio_temp"]
        .transform("median")
    )


    overall_cost_ratio = (
        pnl[f"{col}_ratio_temp"]
        .median()
    )


    platform_cost_ratio = (
        platform_cost_ratio
        .fillna(overall_cost_ratio)
    )


    missing_cost = (
        pnl[col].isna()
        &
        pnl["revenue_inr"].notna()
        &
        (pnl["revenue_inr"] > 0)
    )


    pnl.loc[
        missing_cost,
        col
    ] = (
        pnl.loc[
            missing_cost,
            "revenue_inr"
        ]
        *
        platform_cost_ratio[
            missing_cost
        ]
    )


# ============================================================
# STEP 12 — FILL MISSING ORDERS COUNT
# ============================================================
# The dataset does not provide a strong reliable predictive
# relationship for orders_count.
#
# Therefore use platform-level median orders.


platform_orders_median = (
    pnl.groupby("platform_id")["orders_count"]
    .transform("median")
)


overall_orders_median = (
    pnl["orders_count"]
    .median()
)


pnl["orders_count"] = (
    pnl["orders_count"]
    .fillna(platform_orders_median)
    .fillna(overall_orders_median)
)


# Orders count must be whole numbers.

pnl["orders_count"] = (
    pnl["orders_count"]
    .round()
    .astype("Int64")
)


# ============================================================
# STEP 13 — FINAL FALLBACK FOR MISSING FINANCIAL VALUES
# ============================================================
# In case any value is still missing, use platform-level
# median first and overall median as final fallback.


financial_columns = [
    "revenue_inr",
    "cogs_inr",
    "delivery_cost_inr",
    "marketing_spend_inr",
    "employee_cost_inr",
    "other_opex_inr"
]


for col in financial_columns:

    platform_median = (
        pnl.groupby("platform_id")[col]
        .transform("median")
    )


    pnl[col] = (
        pnl[col]
        .fillna(platform_median)
        .fillna(pnl[col].median())
    )


# ============================================================
# STEP 14 — CALCULATE PROFIT
# ============================================================
# Profit =
# Revenue - COGS - Delivery Cost
#         - Marketing Spend - Employee Cost - Other Opex


pnl["profit_inr"] = (
    pnl["revenue_inr"]
    -
    pnl["cogs_inr"]
    -
    pnl["delivery_cost_inr"]
    -
    pnl["marketing_spend_inr"]
    -
    pnl["employee_cost_inr"]
    -
    pnl["other_opex_inr"]
)


# ============================================================
# STEP 15 — CALCULATE PROFIT MARGIN
# ============================================================

pnl["profit_margin_percent"] = np.where(
    pnl["revenue_inr"] > 0,
    (
        pnl["profit_inr"]
        /
        pnl["revenue_inr"]
        *
        100
    ),
    np.nan
)


# ============================================================
# STEP 16 — CALCULATE COST RATIO
# ============================================================
# Total operating cost as percentage of revenue.


pnl["total_cost_inr"] = (
    pnl["cogs_inr"]
    +
    pnl["delivery_cost_inr"]
    +
    pnl["marketing_spend_inr"]
    +
    pnl["employee_cost_inr"]
    +
    pnl["other_opex_inr"]
)


pnl["cost_to_revenue_percent"] = np.where(
    pnl["revenue_inr"] > 0,
    (
        pnl["total_cost_inr"]
        /
        pnl["revenue_inr"]
        *
        100
    ),
    np.nan
)


# ============================================================
# STEP 17 — CALCULATE AVERAGE ORDER VALUE
# ============================================================
# AOV =
# Revenue / Orders


pnl["aov_inr"] = np.where(
    pnl["orders_count"] > 0,
    (
        pnl["revenue_inr"]
        /
        pnl["orders_count"]
    ),
    np.nan
)


# ============================================================
# STEP 18 — ROUND FINANCIAL VALUES
# ============================================================

round_columns = [
    "revenue_inr",
    "cogs_inr",
    "delivery_cost_inr",
    "marketing_spend_inr",
    "employee_cost_inr",
    "other_opex_inr",
    "profit_inr",
    "profit_margin_percent",
    "total_cost_inr",
    "cost_to_revenue_percent",
    "aov_inr"
]


for col in round_columns:

    pnl[col] = pnl[col].round(2)


# ============================================================
# STEP 19 — REMOVE TEMPORARY COLUMNS
# ============================================================

temporary_columns = [
    "revenue_cogs_ratio_temp"
]


for col in cost_columns:

    temporary_columns.append(
        f"{col}_ratio_temp"
    )


pnl.drop(
    columns=temporary_columns,
    inplace=True,
    errors="ignore"
)


# ============================================================
# STEP 20 — CHECK FOR DUPLICATE BUSINESS KEYS
# ============================================================
# Each platform-city-month should represent one P&L record.

print(
    "\nDuplicate platform-city-month records:",
    pnl.duplicated(
        ["platform_id", "city", "month"]
    ).sum()
)


# ============================================================
# STEP 21 — FINAL DATA QUALITY CHECK
# ============================================================

print("\n========================================")
print("FINAL PNL DATA QUALITY CHECK")
print("========================================")

print(
    "Rows:",
    len(pnl)
)

print(
    "Columns:",
    len(pnl.columns)
)

print(
    "Duplicate rows:",
    pnl.duplicated().sum()
)

print(
    "Duplicate pnl_id:",
    pnl["pnl_id"].duplicated().sum()
)

print(
    "\nRemaining NULL values:"
)

print(
    pnl.isnull().sum()
)


# ============================================================
# STEP 22 — SAVE CLEANED DATA
# ============================================================

pnl.to_csv(
    os.path.join(
        cleaned_folder,
        "10_pnl_monthly_cleaned.csv"
    ),
    index=False
)


# ============================================================
# STEP 23 — DISPLAY CLEANED DATA
# ============================================================

#st.dataframe(pnl)



