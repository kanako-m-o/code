import io
from datetime import date, timedelta
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="同時期・資材購買回数一覧",
    layout="wide",
)

st.title("📦 過去3年間・同時期の資材購買回数一覧（1回 / 2回以上）")


# --- サンプルデータ生成 ---
@st.cache_data
def generate_sample_data(ref_date: date) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    customers = ["株式会社A商事", "B工業株式会社", "C建設", "Dマテリアル", "E製作所"]
    materials = ["養生テープ", "防錆スプレー", "安全帯", "断熱材ボード", "アンカーボルト", "作業用グローブ"]

    records = []
    # 過去4年分のランダム購買＋同時期リピートデータを生成
    for year_offset in range(4):
        target_year = ref_date.year - year_offset
        for _ in range(80):
            base_d = date(target_year, 1, 1) + timedelta(days=int(rng.integers(0, 365)))
            if base_d > ref_date:
                continue
            records.append({
                "購買日": base_d,
                "顧客名": rng.choice(customers),
                "資材名": rng.choice(materials),
                "数量": int(rng.integers(1, 20)) * 10,
            })

    return pd.DataFrame(records).sort_values("購買日", ascending=False).reset_index(drop=True)


# --- ファイル読み込み（UTF-8 / Shift-JIS 自動判定） ---
def load_uploaded_file(uploaded_file) -> pd.DataFrame:
    if uploaded_file.name.endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded_file)

    raw_bytes = uploaded_file.read()
    for encoding in ["utf-8-sig", "utf-8", "cp932", "shift_jis"]:
        try:
            return pd.read_csv(io.BytesIO(raw_bytes), encoding=encoding)
        except UnicodeDecodeError:
            continue
    st.error("ファイルの文字コードを読み取れませんでした。UTF-8またはShift-JISのCSVをご用意ください。")
    st.stop()


# --- 年ごとの基準日生成（うるう年2/29ケア） ---
def safe_replace_year(d: date, year: int) -> date:
    try:
        return d.replace(year=year)
    except ValueError:
        return date(year, 2, 28)


# ================= サイドバー設定 =================
st.sidebar.header("1. データソース")
data_source = st.sidebar.radio("使用するデータ", ["サンプルデータで試す", "CSV / Excelをアップロード"])

today = date.today()

if data_source == "CSV / Excelをアップロード":
    uploaded = st.sidebar.file_uploader("購買履歴ファイルを選択", type=["csv", "xlsx", "xls"])
    if uploaded is None:
        st.info("👈 左のサイドバーから購買履歴ファイル（購買日・顧客名・資材名を含むデータ）をアップロードしてください。")
        st.stop()
    raw_df = load_uploaded_file(uploaded)

    st.sidebar.subheader("列の割り当て")
    cols = raw_df.columns.tolist()
    col_date = st.sidebar.selectbox("購買日の列", cols, index=0)
    col_cust = st.sidebar.selectbox("顧客名の列", cols, index=min(1, len(cols) - 1))
    col_mat = st.sidebar.selectbox("資材名の列", cols, index=min(2, len(cols) - 1))
else:
    raw_df = generate_sample_data(today)
    col_date, col_cust, col_mat = "購買日", "顧客名", "資材名"

st.sidebar.divider()
st.sidebar.header("2. 過去3年・同時期の条件")

ref_date = st.sidebar.date_input("基準日", value=today)
year_scope = st.sidebar.radio(
    "対象とする3年間",
    ["基準年を含む直近3年（今年・昨年・一昨年）", "基準年の前年までの3年（1〜3年前）"],
)

if year_scope.startswith("基準年を含む"):
    target_years = [ref_date.year - i for i in range(3)]
else:
    target_years = [ref_date.year - i for i in range(1, 4)]

period_mode = st.sidebar.radio("同時期の定義方法", ["対象月で指定", "基準日の前後N日間で指定"])

if period_mode == "対象月で指定":
    selected_months = st.sidebar.multiselect(
        "集計する月（複数選択可）",
        options=list(range(1, 13)),
        default=[ref_date.month],
        format_func=lambda m: f"{m}月",
    )
    if not selected_months:
        st.warning("集計する月を1つ以上選択してください。")
        st.stop()
else:
    window_days = st.sidebar.slider("基準日の前後日数（±N日）", min_value=7, max_value=60, value=15, step=1)

count_method = st.sidebar.radio(
    "回数のカウント基準",
    ["購買日ベース（同日の同一資材は1回とみなす）", "明細行ベース（データ行数をそのままカウント）"],
)

# ================= データ前処理・抽出 =================
df = raw_df.copy()
df["_date"] = pd.to_datetime(df[col_date], errors="coerce").dt.date
df = df.dropna(subset=["_date", col_cust, col_mat])

# 対象期間フィルタリング
if period_mode == "対象月で指定":
    mask = df["_date"].apply(lambda d: (d.year in target_years) and (d.month in selected_months) and (d <= ref_date))
    period_label = f"対象年: {', '.join(map(str, sorted(target_years)))}年 / 対象月: {', '.join(f'{m}月' for m in sorted(selected_months))}"
else:
    intervals = []
    for y in target_years:
        center = safe_replace_year(ref_date, y)
        start_d = center - timedelta(days=window_days)
        end_d = min(center + timedelta(days=window_days), ref_date)
        if start_d <= end_d:
            intervals.append((start_d, end_d))

    mask = df["_date"].apply(lambda d: any(s <= d <= e for s, e in intervals))
    interval_strs = [f"{s.strftime('%Y/%m/%d')}〜{e.strftime('%Y/%m/%d')}" for s, e in sorted(intervals)]
    period_label = "抽出期間: " + " / ".join(interval_strs)

filtered_df = df[mask].copy()

st.caption(f"📌 **{period_label}**")

if filtered_df.empty:
    st.warning("指定された同時期の購買データが見つかりませんでした。条件を変更してください。")
    st.stop()

# ================= 集計ロジック =================
filtered_df["購買年"] = filtered_df["_date"].apply(lambda d: str(d.year))

if count_method.startswith("購買日ベース"):
    calc_df = filtered_df.drop_duplicates(subset=[col_cust, col_mat, "_date"])
else:
    calc_df = filtered_df

summary = (
    calc_df.groupby([col_cust, col_mat], as_index=False)
    .agg(
        購買回数=("_date", "count"),
        購買年数=("購買年", "nunique"),
        購買実績年=("購買年", lambda x: ", ".join(sorted(set(x)))),
        最終購買日=("_date", "max"),
    )
)

summary["回数区分"] = np.where(summary["購買回数"] >= 2, "2回以上", "1回")

# 列の並び替え
summary = summary[[col_cust, col_mat, "回数区分", "購買回数", "購買年数", "購買実績年", "最終購買日"]]
summary = summary.sort_values(["回数区分", "購買回数", col_cust], ascending=[False, False, True]).reset_index(drop=True)

# ================= 画面表示・絞り込み =================
col1, col2, col3 = st.columns(3)
total_pairs = len(summary)
repeat_pairs = int((summary["回数区分"] == "2回以上").sum())
once_pairs = int((summary["回数区分"] == "1回").sum())

col1.metric("対象（顧客×資材）総数", f"{total_pairs:,} 件")
col2.metric("🔁 2回以上購買（リピート）", f"{repeat_pairs:,} 件")
col3.metric("1️⃣ 1回のみ購買", f"{once_pairs:,} 件")

st.divider()

f_col1, f_col2, f_col3 = st.columns([1, 1.5, 1.5])
with f_col1:
    selected_cat = st.segmented_control(
        "回数区分フィルタ",
        options=["すべて", "2回以上", "1回"],
        default="すべて",
    )
with f_col2:
    cust_options = sorted(summary[col_cust].unique().tolist())
    selected_custs = st.multiselect("顧客で絞り込み", options=cust_options)
with f_col3:
    mat_keyword = st.text_input("資材名キーワード検索", placeholder="例: テープ")

view_df = summary.copy()
if selected_cat and selected_cat != "すべて":
    view_df = view_df[view_df["回数区分"] == selected_cat]
if selected_custs:
    view_df = view_df[view_df[col_cust].isin(selected_custs)]
if mat_keyword:
    view_df = view_df[view_df[col_mat].astype(str).str.contains(mat_keyword, case=False, na=False)]


# 「2回以上」と「1回」を視覚的に区別するスタイリング
def style_category(val: str) -> str:
    if val == "2回以上":
        return "background-color: #e6f4ea; color: #137333; font-weight: bold;"
    return "background-color: #f1f3f4; color: #3c4043;"


st.dataframe(
    view_df.style.map(style_category, subset=["回数区分"]),
    use_container_width=True,
    hide_index=True,
)

# CSVダウンロード（Excelで文字化けしないBOM付きUTF-8）
csv_bytes = view_df.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    label="📥 表示中の一覧をCSVダウンロード",
    data=csv_bytes,
    file_name=f"同時期購買一覧_{ref_date.strftime('%Y%m%d')}.csv",
    mime="text/csv",
)
