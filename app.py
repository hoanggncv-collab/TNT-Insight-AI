
import io
import re
from datetime import date, datetime

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(
    page_title="TNT Insight AI",
    page_icon="📊",
    layout="wide",
)

# -----------------------------
# Constants & helpers
# -----------------------------
COLUMN_ALIASES = {
    "order_id": [
        "order id", "platform unique order id", "order_id"
    ],
    "created_time": [
        "order created time", "created time", "creation time", "order creation time"
    ],
    "cancel_by": [
        "cancel by", "checked marked by", "cancel_by"
    ],
    "region": [
        "region", "shipping region", "recipient region"
    ],
    "creator": [
        "creator handle", "creator", "affiliate name", "affiliate creator"
    ],
    "order_channel": [
        "order channel", "channel", "traffic source"
    ],
    "product_name": [
        "product name", "seller product name", "product"
    ],
    "seller_sku": [
        "seller sku", "sku", "seller_sku"
    ],
    "price": [
        "sku subtotal after discount", "unit price", "sku unit original price",
        "subtotal after discount", "price"
    ],
    "shipping_fee": [
        "shipping fee", "buyer shipping fee", "shipping fee paid by buyer"
    ],
    "order_status": [
        "order status", "status"
    ],
    "cancel_reason": [
        "cancel reason", "cancellation reason"
    ],
}


def normalize_text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip()).lower()


def find_best_header(raw_df: pd.DataFrame, scan_rows: int = 8) -> int:
    """Find the row most likely to contain headers."""
    best_idx = 0
    best_score = -1
    alias_terms = {alias for aliases in COLUMN_ALIASES.values() for alias in aliases}
    for idx in range(min(scan_rows, len(raw_df))):
        row = [normalize_text(x) for x in raw_df.iloc[idx].tolist()]
        score = sum(any(alias in cell for alias in alias_terms) for cell in row)
        score += len(set(x for x in row if x)) * 0.001
        if score > best_score:
            best_score = score
            best_idx = idx
    return best_idx


@st.cache_data(show_spinner=False)
def read_excel_file(file_bytes: bytes, filename: str) -> pd.DataFrame:
    raw = pd.read_excel(io.BytesIO(file_bytes), header=None, dtype=object, engine="openpyxl")
    header_idx = find_best_header(raw)
    headers = []
    for i, value in enumerate(raw.iloc[header_idx].tolist()):
        text = str(value).strip() if pd.notna(value) else ""
        headers.append(text if text else f"Unnamed_{i+1}")

    df = raw.iloc[header_idx + 1:].copy()
    df.columns = headers
    df = df.dropna(how="all")
    return df.reset_index(drop=True)


def auto_map_columns(df: pd.DataFrame) -> dict:
    normalized = {normalize_text(col): col for col in df.columns}
    mapping = {}
    for key, aliases in COLUMN_ALIASES.items():
        match = None
        for norm_col, original in normalized.items():
            if any(alias == norm_col or alias in norm_col for alias in aliases):
                match = original
                break
        mapping[key] = match
    return mapping


def deduplicate_orders(df: pd.DataFrame, m: dict) -> pd.DataFrame:
    order_col = m.get("order_id")
    if not order_col:
        raise ValueError("Không tìm thấy cột Order ID.")

    work = df.copy()
    work[order_col] = work[order_col].astype(str).str.strip()
    work = work[work[order_col].ne("") & work[order_col].ne("nan")]

    agg = {order_col: "first"}
    for key, col in m.items():
        if col and col != order_col:
            if key == "price":
                agg[col] = "max"
            else:
                agg[col] = lambda s: next((x for x in s if pd.notna(x) and str(x).strip() != ""), np.nan)

    order_df = work.groupby(order_col, as_index=False).agg(agg)

    # Standardized fields
    order_df["_order_id"] = order_df[order_col].astype(str)
    order_df["_created_time"] = pd.to_datetime(order_df[m["created_time"]], errors="coerce") if m.get("created_time") else pd.NaT
    order_df["_cancel_by"] = order_df[m["cancel_by"]].astype(str).str.strip().str.title() if m.get("cancel_by") else ""
    order_df["_region"] = order_df[m["region"]].fillna("Unknown Region").astype(str).str.strip() if m.get("region") else "Unknown Region"
    order_df["_creator"] = order_df[m["creator"]].fillna("").astype(str).str.strip() if m.get("creator") else ""
    order_df["_channel"] = order_df[m["order_channel"]].fillna("").astype(str).str.strip() if m.get("order_channel") else ""
    order_df["_product"] = order_df[m["product_name"]].fillna("Unknown Product").astype(str).str.strip() if m.get("product_name") else "Unknown Product"
    order_df["_sku"] = order_df[m["seller_sku"]].fillna("").astype(str).str.strip() if m.get("seller_sku") else ""
    order_df["_price"] = pd.to_numeric(order_df[m["price"]], errors="coerce") if m.get("price") else np.nan
    order_df["_shipping_fee"] = pd.to_numeric(order_df[m["shipping_fee"]], errors="coerce").fillna(0) if m.get("shipping_fee") else 0

    order_df["_source"] = np.where(
        order_df["_creator"].ne(""),
        order_df["_creator"],
        np.where(order_df["_channel"].str.lower().eq("product cards"), "Product cards", "Unknown")
    )

    return order_df


def metrics(df: pd.DataFrame) -> dict:
    total = len(df)
    user = int(df["_cancel_by"].eq("User").sum())
    system = int(df["_cancel_by"].eq("System").sum())
    shipped = total - user
    return {
        "total": total,
        "user": user,
        "system": system,
        "shipped": shipped,
        "user_rate": user / total if total else 0,
        "dfr": system / shipped if shipped else 0,
        "loss": (user + system) / total if total else 0,
    }


def grouped_metrics(df: pd.DataFrame, field: str) -> pd.DataFrame:
    rows = []
    for value, g in df.groupby(field, dropna=False):
        m = metrics(g)
        rows.append({
            "Group": value if str(value).strip() else "Unknown",
            "Orders": m["total"],
            "User": m["user"],
            "System": m["system"],
            "User Rate": m["user_rate"],
            "DFR": m["dfr"],
            "Order Loss": m["loss"],
            "Fail Contribution": m["system"] / max(1, int(df["_cancel_by"].eq("System").sum())),
        })
    return pd.DataFrame(rows).sort_values(["System", "Orders"], ascending=False)


def classify_product(name: str) -> str:
    text = normalize_text(name)
    if "zencolor" in text or "exfoliating" in text or "peeling gel" in text:
        return "Zencolor / Exfoliating"
    if "foundation" in text or "qise" in text or "vellia" in text:
        return "Foundation"
    return "Other"


def price_band(series: pd.Series) -> pd.Series:
    bins = [-np.inf, 109.999, 119.999, 129.999, 139.999, 149.999, 159.999, np.inf]
    labels = ["≤109", "110–119", "120–129", "130–139", "140–149", "150–159", "≥160"]
    return pd.cut(series, bins=bins, labels=labels)


def fmt_pct(x):
    return f"{x:.2%}"


def show_metric_cards(m):
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Tổng đơn", f"{m['total']:,}")
    c2.metric("User cancel", f"{m['user']:,}", fmt_pct(m["user_rate"]))
    c3.metric("Đơn đã gửi", f"{m['shipped']:,}")
    c4.metric("Delivery Fail", f"{m['system']:,}", fmt_pct(m["dfr"]))
    c5.metric("Order Loss", fmt_pct(m["loss"]))


def display_group_table(table: pd.DataFrame, top_n=20):
    view = table.head(top_n).copy()
    for col in ["User Rate", "DFR", "Order Loss", "Fail Contribution"]:
        if col in view:
            view[col] = view[col].map(lambda x: f"{x:.2%}")
    st.dataframe(view, use_container_width=True, hide_index=True)


def load_timeline_editor():
    st.subheader("Timeline tài khoản quảng cáo / thay đổi vận hành")
    default = pd.DataFrame([
        {"Start": None, "End": None, "Label": "", "Type": "BC"},
    ])
    return st.data_editor(
        default,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Start": st.column_config.DateColumn("Từ ngày"),
            "End": st.column_config.DateColumn("Đến ngày"),
            "Label": st.column_config.TextColumn("Tên tài khoản / sự kiện"),
            "Type": st.column_config.SelectboxColumn("Loại", options=["BC", "Price", "Promotion", "Other"]),
        },
        key="timeline_editor",
    )


def timeline_analysis(df: pd.DataFrame, timeline_df: pd.DataFrame):
    if df["_created_time"].isna().all():
        st.warning("Không có Created Time hợp lệ để phân tích timeline.")
        return
    rows = []
    for _, r in timeline_df.dropna(subset=["Start", "End"]).iterrows():
        start = pd.Timestamp(r["Start"])
        end = pd.Timestamp(r["End"]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        g = df[df["_created_time"].between(start, end)]
        m = metrics(g)
        rows.append({
            "Giai đoạn": f"{start.date()} → {pd.Timestamp(r['End']).date()}",
            "Tên": r.get("Label", ""),
            "Loại": r.get("Type", ""),
            "Tổng đơn": m["total"],
            "User": m["user"],
            "System": m["system"],
            "DFR": m["dfr"],
            "Order Loss": m["loss"],
        })
    if not rows:
        st.info("Nhập ít nhất một khoảng ngày để xem phân tích.")
        return
    result = pd.DataFrame(rows)
    show = result.copy()
    show["DFR"] = show["DFR"].map(lambda x: f"{x:.2%}")
    show["Order Loss"] = show["Order Loss"].map(lambda x: f"{x:.2%}")
    st.dataframe(show, use_container_width=True, hide_index=True)
    fig = px.bar(result, x="Tên", y="DFR", color="Loại", text_auto=".1%", title="DFR theo timeline")
    st.plotly_chart(fig, use_container_width=True)


# -----------------------------
# UI
# -----------------------------
st.title("📊 TNT Insight AI")
st.caption("MVP v0.2 — TikTok Shop Delivery Analytics")

if "run_analysis" not in st.session_state:
    st.session_state.run_analysis = False

if "uploaded_signature" not in st.session_state:
    st.session_state.uploaded_signature = None

with st.sidebar:
    st.header("1. Upload dữ liệu")

    uploaded = st.file_uploader(
        "All Order (.xlsx)",
        type=["xlsx"],
        key="all_order_uploader",
    )

    st.caption("Chọn file, sau đó bấm **Phân tích** để xác nhận.")

    if uploaded is not None:
        signature = (uploaded.name, uploaded.size)
        if st.session_state.uploaded_signature != signature:
            st.session_state.uploaded_signature = signature
            st.session_state.run_analysis = False
        st.success(f"Đã chọn: {uploaded.name}")

    analyze_col, reset_col = st.columns(2)

    with analyze_col:
        if st.button(
            "🚀 Phân tích",
            type="primary",
            use_container_width=True,
            disabled=uploaded is None,
        ):
            st.session_state.run_analysis = True

    with reset_col:
        if st.button("🔄 Reset", use_container_width=True):
            st.session_state.run_analysis = False
            st.session_state.uploaded_signature = None
            st.cache_data.clear()
            st.rerun()

    st.divider()
    st.header("2. Công thức")
    st.code("DFR = System / (Tổng đơn − User)")
    st.code("Order Loss = (User + System) / Tổng đơn")

if uploaded is None:
    st.info("Upload file **All Order**, sau đó bấm **🚀 Phân tích**.")

    st.markdown("""
### MVP hiện có
- Tổng quan DFR / User / Order Loss
- Region, Creator, Product, Pricing
- Timeline tài khoản quảng cáo theo ngày tạo đơn
- Xuất bảng Excel
""")
    st.stop()

if not st.session_state.run_analysis:
    st.info("📁 File đã sẵn sàng. Bấm **🚀 Phân tích** ở thanh bên trái để bắt đầu.")
    st.stop()

with st.spinner("Đang đọc và xử lý dữ liệu..."):
    file_bytes = uploaded.getvalue()

try:
    df_raw = read_excel_file(file_bytes, uploaded.name)
except Exception as exc:
    st.error(f"Không đọc được file: {exc}")
    st.stop()

mapping = auto_map_columns(df_raw)

with st.expander("Kiểm tra / chỉnh mapping cột", expanded=False):
    cols = ["— Không dùng —"] + list(df_raw.columns)
    edited = {}
    labels = {
        "order_id": "Order ID",
        "created_time": "Order Created Time",
        "cancel_by": "Cancel By (User/System)",
        "region": "Region",
        "creator": "Creator Handle",
        "order_channel": "Order Channel",
        "product_name": "Product Name",
        "seller_sku": "Seller SKU",
        "price": "Price / SKU Subtotal After Discount",
        "shipping_fee": "Shipping Fee",
        "order_status": "Order Status",
        "cancel_reason": "Cancel Reason",
    }
    for key in labels:
        current = mapping.get(key)
        index = cols.index(current) if current in cols else 0
        selected = st.selectbox(labels[key], cols, index=index, key=f"map_{key}")
        edited[key] = None if selected == "— Không dùng —" else selected
    mapping = edited

try:
    orders = deduplicate_orders(df_raw, mapping)
except Exception as exc:
    st.error(str(exc))
    st.stop()

orders["_product_group"] = orders["_product"].map(classify_product)
orders["_price_band"] = price_band(orders["_price"])

# Filters
with st.sidebar:
    st.header("3. Bộ lọc")
    date_min = orders["_created_time"].min()
    date_max = orders["_created_time"].max()
    if pd.notna(date_min) and pd.notna(date_max):
        selected_dates = st.date_input(
            "Khoảng ngày tạo đơn",
            value=(date_min.date(), date_max.date()),
            min_value=date_min.date(),
            max_value=date_max.date(),
        )
    else:
        selected_dates = None

    products = ["Tất cả"] + sorted(orders["_product_group"].dropna().unique().tolist())
    selected_product = st.selectbox("Nhóm sản phẩm", products)

filtered = orders.copy()
if selected_dates and isinstance(selected_dates, tuple) and len(selected_dates) == 2:
    start, end = map(pd.Timestamp, selected_dates)
    filtered = filtered[filtered["_created_time"].between(start, end + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))]
if selected_product != "Tất cả":
    filtered = filtered[filtered["_product_group"].eq(selected_product)]

tabs = st.tabs(["Tổng quan", "Region", "Creator", "Product", "Pricing", "BC Timeline", "Xuất dữ liệu"])

with tabs[0]:
    st.subheader("Tổng quan")
    m = metrics(filtered)
    show_metric_cards(m)

    if not filtered["_created_time"].isna().all():
        daily = filtered.assign(Date=filtered["_created_time"].dt.date).groupby("Date").apply(
            lambda g: pd.Series(metrics(g))
        ).reset_index()
        fig = px.line(daily, x="Date", y="dfr", markers=True, title="DFR theo ngày tạo đơn")
        fig.update_yaxes(tickformat=".1%")
        st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        product_table = grouped_metrics(filtered, "_product_group")
        fig = px.bar(product_table, x="Group", y="DFR", text_auto=".1%", title="DFR theo sản phẩm")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        source_table = grouped_metrics(filtered, "_channel")
        fig = px.bar(source_table.head(10), x="Group", y="DFR", text_auto=".1%", title="DFR theo kênh")
        st.plotly_chart(fig, use_container_width=True)

with tabs[1]:
    st.subheader("Region")
    region_table = grouped_metrics(filtered, "_region")
    display_group_table(region_table, 50)
    fig = px.scatter(
        region_table.head(30),
        x="Orders",
        y="DFR",
        size="System",
        hover_name="Group",
        title="Region: Quy mô đơn vs DFR",
    )
    fig.update_yaxes(tickformat=".1%")
    st.plotly_chart(fig, use_container_width=True)

with tabs[2]:
    st.subheader("Creator / Traffic Source")
    creator_table = grouped_metrics(filtered, "_source")
    display_group_table(creator_table, 50)
    fig = px.scatter(
        creator_table.head(50),
        x="Orders",
        y="DFR",
        size="System",
        hover_name="Group",
        title="Creator: Quy mô đơn vs DFR",
    )
    fig.update_yaxes(tickformat=".1%")
    st.plotly_chart(fig, use_container_width=True)

with tabs[3]:
    st.subheader("Product")
    product_table = grouped_metrics(filtered, "_product_group")
    display_group_table(product_table, 20)

    selected_detail = st.selectbox("Chọn nhóm sản phẩm để đào sâu", sorted(filtered["_product_group"].unique()))
    detail = filtered[filtered["_product_group"].eq(selected_detail)]
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Top Region")
        display_group_table(grouped_metrics(detail, "_region"), 20)
    with c2:
        st.markdown("#### Top Creator")
        display_group_table(grouped_metrics(detail, "_source"), 20)

with tabs[4]:
    st.subheader("Pricing")
    valid_price = filtered[filtered["_price"].notna()].copy()
    if valid_price.empty:
        st.warning("Không tìm thấy cột giá hợp lệ.")
    else:
        pricing = grouped_metrics(valid_price, "_price_band")
        pricing["Sort"] = pricing["Group"].astype(str).map(
            {"≤109": 1, "110–119": 2, "120–129": 3, "130–139": 4, "140–149": 5, "150–159": 6, "≥160": 7}
        )
        pricing = pricing.sort_values("Sort")
        display_group_table(pricing.drop(columns=["Sort"]), 20)
        fig = px.bar(pricing, x="Group", y="DFR", text_auto=".1%", title="DFR theo khoảng giá")
        fig.update_yaxes(tickformat=".1%")
        st.plotly_chart(fig, use_container_width=True)

with tabs[5]:
    timeline_df = load_timeline_editor()
    timeline_analysis(filtered, timeline_df)

with tabs[6]:
    st.subheader("Xuất dữ liệu")
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        filtered.to_excel(writer, sheet_name="Cleaned_Orders", index=False)
        grouped_metrics(filtered, "_region").to_excel(writer, sheet_name="Region", index=False)
        grouped_metrics(filtered, "_source").to_excel(writer, sheet_name="Creator", index=False)
        grouped_metrics(filtered, "_product_group").to_excel(writer, sheet_name="Product", index=False)
        if filtered["_price"].notna().any():
            grouped_metrics(filtered, "_price_band").to_excel(writer, sheet_name="Pricing", index=False)
    st.download_button(
        "Tải Excel phân tích",
        data=buffer.getvalue(),
        file_name="TNT_Insight_Export.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
