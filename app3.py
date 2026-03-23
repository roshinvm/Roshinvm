import streamlit as st
import sqlite3
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from prophet import Prophet

# -------- NEW IMPORTS FOR MILESTONE 4 --------
import io
from fpdf import FPDF
import psutil
import platform

# ---------------- DATABASE ----------------
conn = sqlite3.connect("app.db", check_same_thread=False)
cursor = conn.cursor()

# Users
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT
)
""")

# Inventory
cursor.execute("""
CREATE TABLE IF NOT EXISTS inventory (
    username TEXT,
    product TEXT,
    stock REAL,
    PRIMARY KEY (username, product)
)
""")

# Sales
cursor.execute("""
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    product TEXT,
    quantity REAL,
    selling_price REAL,
    cost_price REAL,
    revenue REAL,
    cogs REAL,
    profit REAL,
    date TEXT
)
""")

conn.commit()

# ---------------- HELPERS ----------------
def norm(x):
    return str(x).strip().lower()

def register(u,p):
    try:
        cursor.execute("INSERT INTO users (username,password) VALUES (?,?)",(u,p))
        conn.commit()
        return True
    except:
        return False

def login(u,p):
    cursor.execute("SELECT * FROM users WHERE username=? AND password=?",(u,p))
    return cursor.fetchone()

def add_stock(user,product,qty):
    product=norm(product)
    cursor.execute("SELECT stock FROM inventory WHERE username=? AND product=?",(user,product))
    r=cursor.fetchone()
    if r:
        cursor.execute("UPDATE inventory SET stock=? WHERE username=? AND product=?",(r[0]+qty,user,product))
    else:
        cursor.execute("INSERT INTO inventory VALUES (?,?,?)",(user,product,qty))
    conn.commit()

def reduce_stock(user,product,qty):
    product=norm(product)
    cursor.execute("SELECT stock FROM inventory WHERE username=? AND product=?",(user,product))
    r=cursor.fetchone()
    if r:
        cursor.execute("UPDATE inventory SET stock=? WHERE username=? AND product=?",(r[0]-qty,user,product))
        conn.commit()

# ---------------- SESSION ----------------
if "logged" not in st.session_state:
    st.session_state.logged=False
if "user" not in st.session_state:
    st.session_state.user=""

# ---------------- MENU ----------------
if st.session_state.logged:
    menu=st.sidebar.selectbox("Menu",
        ["Dashboard","Add Stock","Add Sales",
         "Linear Regression Forecast","Prophet Forecast",
         "Reports","Admin Dashboard","Logout"])
else:
    menu=st.sidebar.selectbox("Menu",["Login","Register"])

# ---------------- LOGIN ----------------
if menu=="Login":
    st.title("🔐 Login")
    u=st.text_input("Username")
    p=st.text_input("Password",type="password")
    if st.button("Login"):
        if login(u,p):
            st.session_state.logged=True
            st.session_state.user=u
            st.success("Logged in")
        else:
            st.error("Invalid credentials")

# ---------------- REGISTER ----------------
elif menu=="Register":
    st.title("📝 Register")
    u=st.text_input("Username")
    p=st.text_input("Password",type="password")
    if st.button("Create"):
        if register(u,p):
            st.success("Account created")
        else:
            st.error("Username already exists")

# ---------------- ADD STOCK ----------------
elif menu=="Add Stock":
    st.title("📦 Add / Upload Stock")
    user=st.session_state.user

    st.subheader("Manual Entry")
    p=st.text_input("Product")
    q=st.number_input("Quantity",min_value=0.0)
    if st.button("Add Stock"):
        add_stock(user,p,q)
        st.success("Stock Added")

    st.subheader("Upload CSV / XLSX")
    file=st.file_uploader("Upload File",type=["csv","xlsx"])
    if file:
        df=pd.read_csv(file) if file.name.endswith("csv") else pd.read_excel(file)
        df.columns=df.columns.str.lower().str.strip()

        if "product" in df.columns and "quantity" in df.columns:
            for _,r in df.iterrows():
                add_stock(user,r["product"],r["quantity"])
            st.success("Stock Uploaded Successfully")
        else:
            st.error("File must contain: product, quantity columns")

    st.subheader("Current Inventory")
    st.dataframe(pd.read_sql("SELECT * FROM inventory WHERE username=?",
                             conn,params=(user,)))

# ---------------- ADD SALES ----------------
elif menu=="Add Sales":
    st.title("🛒 Add / Upload Sales")
    user=st.session_state.user

    st.subheader("Manual Sale")
    p=st.text_input("Product")
    q=st.number_input("Quantity",min_value=0.0)
    sp=st.number_input("Selling Price",min_value=0.0)
    cp=st.number_input("Cost Price",min_value=0.0)
    d=st.date_input("Date")

    if st.button("Add Sale"):
        rev=q*sp
        cogs=q*cp
        profit=rev-cogs
        reduce_stock(user,p,q)

        cursor.execute("""
        INSERT INTO sales (username,product,quantity,selling_price,
        cost_price,revenue,cogs,profit,date)
        VALUES (?,?,?,?,?,?,?,?,?)
        """,(user,norm(p),q,sp,cp,rev,cogs,profit,str(d)))
        conn.commit()
        st.success("Sale Added")

    st.subheader("Upload CSV / XLSX")
    file=st.file_uploader("Upload Sales File",type=["csv","xlsx"])
    if file:
        df=pd.read_csv(file) if file.name.endswith("csv") else pd.read_excel(file)
        df.columns=df.columns.str.lower().str.strip().str.replace("_"," ")

        required=["date","product","quantity","selling price","cost price"]

        if all(col in df.columns for col in required):

            df["date"]=pd.to_datetime(df["date"],errors="coerce")
            df["product"]=df["product"].apply(norm)

            df["revenue"]=df["quantity"]*df["selling price"]
            df["cogs"]=df["quantity"]*df["cost price"]
            df["profit"]=df["revenue"]-df["cogs"]
            df["username"]=user

            for _,r in df.iterrows():
                reduce_stock(user,r["product"],r["quantity"])

            df_db=df.rename(columns={
                "selling price":"selling_price",
                "cost price":"cost_price"
            })

            df_db.to_sql("sales",conn,if_exists="append",index=False)
            st.success("Sales Uploaded Successfully")

        else:
            st.error("File must contain: date, product, quantity, selling price, cost price")

# ---------------- DASHBOARD ----------------
elif menu=="Dashboard":
    st.title("📊 Dashboard")
    user=st.session_state.user

    df_sales=pd.read_sql("SELECT * FROM sales WHERE username=?",
                         conn,params=(user,))

    if not df_sales.empty:
        df_sales["date"]=pd.to_datetime(df_sales["date"])
        daily=df_sales.groupby("date")[["revenue","profit"]].sum()
        st.subheader("Revenue & Profit Trend")
        st.line_chart(daily)

        st.subheader("Profit by Product")
        st.bar_chart(df_sales.groupby("product")["profit"].sum())

        c1,c2,c3=st.columns(3)
        c1.metric("Revenue",f"₹ {df_sales['revenue'].sum():,.0f}")
        c2.metric("COGS",f"₹ {df_sales['cogs'].sum():,.0f}")
        c3.metric("Profit",f"₹ {df_sales['profit'].sum():,.0f}")

# ---------------- LINEAR REGRESSION ----------------
elif menu=="Linear Regression Forecast":
    st.title("📈 Linear Regression Forecast")
    user=st.session_state.user

    df_sales=pd.read_sql("SELECT * FROM sales WHERE username=?",
                         conn,params=(user,))
    if df_sales.empty:
        st.warning("No sales data")
    else:
        df_sales["date"]=pd.to_datetime(df_sales["date"])
        daily=df_sales.groupby("date")["revenue"].sum().reset_index()

        daily["day"]=(daily["date"]-daily["date"].min()).dt.days

        model=LinearRegression()
        model.fit(daily[["day"]],daily["revenue"])

        future=np.arange(daily["day"].max()+1,
                         daily["day"].max()+31)

        preds=model.predict(pd.DataFrame({"day":future}))

        st.line_chart(daily.set_index("date")["revenue"])
        st.success(f"Next 30 Days Estimated Revenue: ₹ {preds.sum():,.0f}")

# ---------------- PROPHET FORECAST ----------------
elif menu=="Prophet Forecast":
    st.title("🔮 Prophet Forecast")
    user=st.session_state.user

    df_sales=pd.read_sql("SELECT * FROM sales WHERE username=?",
                         conn,params=(user,))
    if df_sales.empty:
        st.warning("No sales data")
    else:
        df_sales["date"]=pd.to_datetime(df_sales["date"])
        daily=df_sales.groupby("date")["revenue"].sum().reset_index()

        prophet_df=daily.rename(columns={"date":"ds","revenue":"y"})

        model=Prophet()
        model.fit(prophet_df)

        future=model.make_future_dataframe(periods=30)
        forecast=model.predict(future)

        st.line_chart(forecast.set_index("ds")[["yhat"]])

# ---------------- REPORT GENERATION ----------------
elif menu=="Reports":

    st.title("📑 Report Generation")
    user=st.session_state.user

    df_sales=pd.read_sql("SELECT * FROM sales WHERE username=?",
                         conn,params=(user,))

    if df_sales.empty:
        st.warning("No sales data")
    else:

        st.dataframe(df_sales)

        # Excel
        excel_buffer=io.BytesIO()
        df_sales.to_excel(excel_buffer,index=False)

        st.download_button(
            label="Download Excel Report",
            data=excel_buffer.getvalue(),
            file_name="sales_report.xlsx"
        )

        # PDF
        pdf=FPDF()
        pdf.add_page()
        pdf.set_font("Arial",size=12)

        pdf.cell(200,10,"Sales Report",ln=True)

        for i,row in df_sales.iterrows():
            line=f"{row['date']} | {row['product']} | Qty:{row['quantity']} | Profit:{row['profit']}"
            pdf.cell(200,8,line,ln=True)

        pdf_output=pdf.output(dest="S").encode("latin-1")

        st.download_button(
            label="Download PDF Report",
            data=pdf_output,
            file_name="sales_report.pdf"
        )

# ---------------- ADMIN DASHBOARD ----------------
elif menu=="Admin Dashboard":

    st.title("⚙ Admin Dashboard")

    users=pd.read_sql("SELECT * FROM users",conn)
    sales=pd.read_sql("SELECT * FROM sales",conn)
    inventory=pd.read_sql("SELECT * FROM inventory",conn)

    c1,c2,c3=st.columns(3)

    c1.metric("Active Users",len(users))
    c2.metric("Business Profiles",sales["username"].nunique() if not sales.empty else 0)
    c3.metric("Total Products",len(inventory))

    st.subheader("Users")
    st.dataframe(users)

    st.subheader("System Monitoring")

    cpu=psutil.cpu_percent()
    mem=psutil.virtual_memory().percent

    c1,c2=st.columns(2)
    c1.metric("CPU Usage",f"{cpu}%")
    c2.metric("Memory Usage",f"{mem}%")

    st.info(f"System: {platform.system()} | Processor: {platform.processor()}")

    st.success("Deployment Status: LIVE")

# ---------------- LOGOUT ----------------
elif menu=="Logout":
    st.session_state.logged=False
    st.session_state.user=""
    st.success("Logged out")