import io
from datetime import date, timedelta
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="同時期・物品受注回数一覧",
    layout="wide",
)

st.title("📦 過去3年間・同時期の物品受注回数一覧（1回 / 2回以上）")


# --- サンプルデータ生成 ---
@st.cache_data
def generate_sample_data(ref_date: date) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    destinations = ["株式会社A商事", "B工業株式会社", "C建設", "Dマテリアル", "E製作所"]
    items = ["養生テープ", "防錆スプレー", "安全帯", "断熱材ボード", "アンカーボルト", "作業用グローブ"]
    staff_codes = ["S001", "S002", "S003", "S004"]

    records = []
    # 過去4年分のランダム受注データを生成
    for year_offset in range(4):
        target_year = ref_date.year - year_offset
        for _ in range(90):
            base_d = date(target_year, 1, 1) + timedelta(days=int(rng.integers(0, 365)))
            if base_d > ref_date:
                continue

            sales = int(rng.integers(5, 150)) * 1000
            margin_rate = rng.uniform(0.15, 0.40)
            cost = int(round(sales * (1 - margin_rate), -2))

            records.append({
                "受注年月日": base_d,
                "物品名": rng.choice(items),
                "納品先名": rng.choice(destinations),
                "担当者コード": rng.choice(staff_codes),
                "売上金額": sales,
                "仕入金額": cost,
            })

    return pd.DataFrame(records).sort_values("受注年月日", ascending=False).reset_index(drop=True)


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


# --- 列の初期インデックス自動推定 ---
def guess_col_index(cols: list[str], target_name: str, fallback_idx: int) -> int:
    if target_name in cols:
        return cols.index(target_name)
    return min(fallback_idx, len(cols) - 1)


# --- 金額文字列の数値変換（カンマや通貨記号を除去） ---
def to_numeric_clean(series: pd.Series) -> pd.Series:
    cleaned = (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("¥", "", regex=False)
        .str.replace("￥", "", regex=False)
        .str.strip()
    )
    return pd.to_numeric(cleaned, errors="coerce").fillna(0)


# --- 年ごとの基準日生成（うるう年2/29ケア） ---
def safe_replace_year(d: date, year: int) -> date:
    try:
        return d.replace(year=year)
    except ValueError:
        return date(year, 2, 28)


# --- 明細データ整形用ヘルパー ---
def format_detail_df(source_df: pd.DataFrame, include_pair_cols: bool = False) -> pd.DataFrame:
    cols = ["_date", "納品先名", "物品名", "担当者コード", "売上金額", "仕入金額"] if include_pair_cols else [
        "_date",
        "担当者コード",
        "売上金額",
        "仕入金額",
    ]
    detail = source_df[cols].copy()
    detail = detail.rename(columns={"_date": "受注年月日"})
    detail["粗利金額"] = detail["売上金額"] - detail["仕入金額"]
    detail["粗利率(%)"] = np.where(
        detail["売上金額"] != 0,
        (detail["粗利金額"] / detail["売上金額"] * 100).round(1),
        0.0,
    )
    return detail.sort_values("受注年月日", ascending=False).reset_index(drop=True)


# --- 共通：単一案件の明細ビュー描画 ---
def render_single_item_detail(
    period_detail_df: pd.DataFrame,
    all_detail_df: pd.DataFrame,
    sel_dest: str,
    sel_item: str,
    detail_format: dict[str, str],
    key_prefix: str,
    use_switcher: bool = False,
) -> None:
    st.markdown(f"**対象:** {sel_dest} × {sel_item}")

    if use_switcher:
        ctrl_col, note_col = st.columns([1.4, 2.6])
        with ctrl_col:
            scope_choice = st.segmented_control(
                "表示する明細期間",
                options=["指定同時期", "全期間（参考）"],
                default="指定同時期",
                key=f"{key_prefix}_scope",
            )
        with note_col:
            if scope_choice == "全期間（参考）":
                st.caption("※ 同時期以外の月も含めた、基準日以前の全受注データです（担当者絞り込みがある場合は反映）。")
            else:
                st.caption("※ サイドバーで指定した「過去3年・同時期」の条件に一致する受注明細です。")

        if scope_choice == "全期間（参考）":
            target_df = all_detail_df
            scope_tag = "全期間"
            file_suffix = "全期間"
        else:
            target_df = period_detail_df
            scope_tag = "同時期"
            file_suffix = "同時期"

        c1, c2, c3 = st.columns(3)
        c1.metric(f"{scope_tag} 明細行数", f"{len(target_df):,} 行")
        c2.metric(f"{scope_tag} 売上合計", f"¥{int(target_df['売上金額'].sum()):,}")
        c3.metric(f"{scope_tag} 粗利合計", f"¥{int(target_df['粗利金額'].sum()):,}")

        st.dataframe(
            target_df.style.format(detail_format),
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            label=f"📥 この明細（{scope_tag}）をCSVダウンロード",
            data=target_df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"受注明細_{file_suffix}_{sel_dest}_{sel_item}.csv",
            mime="text/csv",
            key=f"{key_prefix}_dl_{file_suffix}",
        )
    else:
        tab1, tab2 = st.tabs([
            f"📅 指定同時期の明細（{len(period_detail_df)}件）",
            f"🗂️ 全期間の受注明細・参考（{len(all_detail_df)}件）",
        ])

        with tab1:
            d_col1, d_col2, d_col3 = st.columns(3)
            d_col1.metric("同時期 明細行数", f"{len(period_detail_df):,} 行")
            d_col2.metric("同時期 売上合計", f"¥{int(period_detail_df['売上金額'].sum()):,}")
            d_col3.metric("同時期 粗利合計", f"¥{int(period_detail_df['粗利金額'].sum()):,}")

            st.dataframe(
                period_detail_df.style.format(detail_format),
                use_container_width=True,
                hide_index=True,
            )

            st.download_button(
                label="📥 この受注明細（同時期）をCSVダウンロード",
                data=period_detail_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"受注明細_同時期_{sel_dest}_{sel_item}.csv",
                mime="text/csv",
                key=f"{key_prefix}_dl_period",
            )

        with tab2:
            st.caption("※ 同時期以外の月も含めた、基準日以前の全受注データです（担当者絞り込みがある場合は反映）。")
            a_col1, a_col2, a_col3 = st.columns(3)
            a_col1.metric("全期間 明細行数", f"{len(all_detail_df):,} 行")
            a_col2.metric("全期間 売上合計", f"¥{int(all_detail_df['売上金額'].sum()):,}")
            a_col3.metric("全期間 粗利合計", f"¥{int(all_detail_df['粗利金額'].sum()):,}")

            st.dataframe(
                all_detail_df.style.format(detail_format),
                use_container_width=True,
                hide_index=True,
            )

            st.download_button(
                label="📥 この受注明細（全期間）をCSVダウンロード",
                data=all_detail_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"受注明細_全期間_{sel_dest}_{sel_item}.csv",
                mime="text/csv",
                key=f"{key_prefix}_dl_all",
            )


# ================= サイドバー設定 =================
st.sidebar.header("1. データソース")
data_source = st.sidebar.radio("使用するデータ", ["サンプルデータで試す", "CSV / Excelをアップロード"])

today = date.today()

if data_source == "CSV / Excelをアップロード":
    uploaded = st.sidebar.file_uploader(
        "受注履歴ファイルを選択",
        type=["csv", "xlsx", "xls"],
    )
    if uploaded is None:
        st.info(
            "👈 左のサイドバーから受注履歴ファイル"
            "（受注年月日・物品名・納品先名・担当者コード・売上金額・仕入金額を含むデータ）"
            "をアップロードしてください。"
        )
        st.stop()

    raw_df = load_uploaded_file(uploaded)
    cols = raw_df.columns.tolist()

    if len(cols) < 6:
        st.warning("アップロードされたファイルの列数が6列未満です。各項目に正しい列を割り当ててください。")

    st.sidebar.subheader("列の割り当て")
    col_date = st.sidebar.selectbox("受注年月日の列", cols, index=guess_col_index(cols, "受注年月日", 0))
    col_item = st.sidebar.selectbox("物品名の列", cols, index=guess_col_index(cols, "物品名", 1))
    col_dest = st.sidebar.selectbox("納品先名の列", cols, index=guess_col_index(cols, "納品先名", 2))
    col_staff = st.sidebar.selectbox("担当者コードの列", cols, index=guess_col_index(cols, "担当者コード", 3))
    col_sales = st.sidebar.selectbox("売上金額の列", cols, index=guess_col_index(cols, "売上金額", 4))
    col_cost = st.sidebar.selectbox("仕入金額の列", cols, index=guess_col_index(cols, "仕入金額", 5))
else:
    raw_df = generate_sample_data(today)
    col_date = "受注年月日"
    col_item = "物品名"
    col_dest = "納品先名"
    col_staff = "担当者コード"
    col_sales = "売上金額"
    col_cost = "仕入金額"

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
    ["受注日ベース（同日の同一納品先・物品は1回とみなす）", "明細行ベース（データ行数をそのままカウント）"],
)

# ================= データ前処理・抽出 =================
df = pd.DataFrame({
    "_date": pd.to_datetime(raw_df[col_date], errors="coerce").dt.date,
    "納品先名": raw_df[col_dest].astype(str).str.strip(),
    "物品名": raw_df[col_item].astype(str).str.strip(),
    "担当者コード": raw_df[col_staff].fillna("未設定").astype(str).str.strip(),
    "売上金額": to_numeric_clean(raw_df[col_sales]),
    "仕入金額": to_numeric_clean(raw_df[col_cost]),
})

# 欠損値の除外
df = df.dropna(subset=["_date"])
df = df[(df["納品先名"] != "") & (df["納品先名"] != "nan") & (df["物品名"] != "") & (df["物品名"] != "nan")]

# 対象期間フィルタリング
if period_mode == "対象月で指定":
    mask = df["_date"].apply(lambda d: (d.year in target_years) and (d.month in selected_months) and (d <= ref_date))
    period_label = (
        f"対象年: {', '.join(map(str, sorted(target_years)))}年 / "
        f"対象月: {', '.join(f'{m}月' for m in sorted(selected_months))}"
    )
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
    st.warning("指定された同時期の受注データが見つかりませんでした。条件を変更してください。")
    st.stop()

# 担当者コードでの事前絞り込み
f_top1, f_top2, f_top3, f_top4 = st.columns([1.1, 1.2, 1.4, 1.3])
with f_top2:
    staff_options = sorted(filtered_df["担当者コード"].unique().tolist())
    selected_staffs = st.multiselect("担当者コードで絞り込み", options=staff_options)

if selected_staffs:
    filtered_df = filtered_df[filtered_df["担当者コード"].isin(selected_staffs)]
    if filtered_df.empty:
        st.warning("選択された担当者コードに該当する受注データがありません。")
        st.stop()

# ================= 集計ロジック =================
filtered_df["受注年"] = filtered_df["_date"].apply(lambda d: str(d.year))
filtered_df = filtered_df.sort_values("_date", ascending=True)

if count_method.startswith("受注日ベース"):
    count_series = filtered_df.groupby(["納品先名", "物品名"])["_date"].nunique()
else:
    count_series = filtered_df.groupby(["納品先名", "物品名"])["_date"].size()

summary = (
    filtered_df.groupby(["納品先名", "物品名"], as_index=False)
    .agg(
        担当者コード=("担当者コード", lambda x: ", ".join(sorted(set(x)))),
        受注年数=("受注年", "nunique"),
        受注実績年=("受注年", lambda x: ", ".join(sorted(set(x)))),
        最終受注日=("_date", "max"),
        売上金額合計=("売上金額", "sum"),
        仕入金額合計=("仕入金額", "sum"),
    )
)

summary = summary.merge(
    count_series.rename("受注回数").reset_index(),
    on=["納品先名", "物品名"],
    how="left",
)

summary["粗利金額合計"] = summary["売上金額合計"] - summary["仕入金額合計"]
summary["粗利率(%)"] = np.where(
    summary["売上金額合計"] != 0,
    (summary["粗利金額合計"] / summary["売上金額合計"] * 100).round(1),
    0.0,
)
summary["回数区分"] = np.where(summary["受注回数"] >= 2, "2回以上", "1回")

# 列の並び替え
display_cols = [
    "納品先名",
    "物品名",
    "担当者コード",
    "回数区分",
    "受注回数",
    "受注年数",
    "受注実績年",
    "最終受注日",
    "売上金額合計",
    "仕入金額合計",
    "粗利金額合計",
    "粗利率(%)",
]
summary = summary[display_cols].sort_values(
    ["回数区分", "受注回数", "売上金額合計", "納品先名"],
    ascending=[False, False, False, True],
).reset_index(drop=True)

# ================= 画面フィルタ（残りの項目） =================
with f_top1:
    selected_cat = st.segmented_control(
        "回数区分フィルタ",
        options=["すべて", "2回以上", "1回"],
        default="すべて",
    )
with f_top3:
    dest_options = sorted(summary["納品先名"].unique().tolist())
    selected_dests = st.multiselect("納品先名で絞り込み", options=dest_options)
with f_top4:
    item_keyword = st.text_input("物品名キーワード検索", placeholder="例: テープ")

view_df = summary.copy()
if selected_cat and selected_cat != "すべて":
    view_df = view_df[view_df["回数区分"] == selected_cat]
if selected_dests:
    view_df = view_df[view_df["納品先名"].isin(selected_dests)]
if item_keyword:
    view_df = view_df[view_df["物品名"].astype(str).str.contains(item_keyword, case=False, na=False)]

# 行選択の位置ズレを防ぐためインデックスを振り直す
view_df = view_df.reset_index(drop=True)

# ================= KPIメトリクス表示 =================
m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns(5)
total_pairs = len(view_df)
repeat_pairs = int((view_df["回数区分"] == "2回以上").sum())
once_pairs = int((view_df["回数区分"] == "1回").sum())
total_sales = int(view_df["売上金額合計"].sum())
total_profit = int(view_df["粗利金額合計"].sum())

m_col1.metric("対象（納品先×物品）数", f"{total_pairs:,} 件")
m_col2.metric("🔁 2回以上受注（リピート）", f"{repeat_pairs:,} 件")
m_col3.metric("1️⃣ 1回のみ受注", f"{once_pairs:,} 件")
m_col4.metric("💰 売上金額合計", f"¥{total_sales:,}")
m_col5.metric("📈 粗利金額合計", f"¥{total_profit:,}")

st.divider()
st.caption(
    "💡 **一覧の左端にあるチェックボックスに複数チェックを入れると、"
    "選択した件数分だけ下にドリルダウンのタブが増えます。**"
)


# 「2回以上」と「1回」を視覚的に区別するスタイリング
def style_category(val: str) -> str:
    if val == "2回以上":
        return "background-color: #e6f4ea; color: #137333; font-weight: bold;"
    return "background-color: #f1f3f4; color: #3c4043;"


styled_df = (
    view_df.style
    .map(style_category, subset=["回数区分"])
    .format({
        "受注回数": "{:,}",
        "受注年数": "{:,}",
        "売上金額合計": "¥{:,.0f}",
        "仕入金額合計": "¥{:,.0f}",
        "粗利金額合計": "¥{:,.0f}",
        "粗利率(%)": "{:.1f}%",
    })
)

# 複数行選択イベントを受け取るデータフレーム表示
selection_event = st.dataframe(
    styled_df,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="multi-row",
)

# CSVダウンロード（Excelで文字化けしないBOM付きUTF-8）
csv_bytes = view_df.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    label="📥 表示中の一覧をCSVダウンロード",
    data=csv_bytes,
    file_name=f"同時期受注一覧_{ref_date.strftime('%Y%m%d')}.csv",
    mime="text/csv",
)

# ================= 選択行の受注明細ドリルダウン表示（複数チェック対応） =================
selected_rows = sorted({idx for idx in selection_event.selection.rows if 0 <= idx < len(view_df)})

detail_format = {
    "売上金額": "¥{:,.0f}",
    "仕入金額": "¥{:,.0f}",
    "粗利金額": "¥{:,.0f}",
    "粗利率(%)": "{:.1f}%",
}

if selected_rows:
    selected_pairs = [
        (view_df.loc[idx, "納品先名"], view_df.loc[idx, "物品名"])
        for idx in selected_rows
    ]

    st.divider()
    with st.expander(f"🔍 選択中の受注明細ドリルダウン（{len(selected_pairs)}件選択中）", expanded=True):
        if len(selected_pairs) == 1:
            sel_dest, sel_item = selected_pairs[0]
            period_detail_raw = filtered_df[
                (filtered_df["納品先名"] == sel_dest) & (filtered_df["物品名"] == sel_item)
            ]
            period_detail_df = format_detail_df(period_detail_raw)

            all_detail_raw = df[
                (df["納品先名"] == sel_dest)
                & (df["物品名"] == sel_item)
                & (df["_date"] <= ref_date)
            ]
            if selected_staffs:
                all_detail_raw = all_detail_raw[all_detail_raw["担当者コード"].isin(selected_staffs)]
            all_detail_df = format_detail_df(all_detail_raw)

            render_single_item_detail(
                period_detail_df=period_detail_df,
                all_detail_df=all_detail_df,
                sel_dest=sel_dest,
                sel_item=sel_item,
                detail_format=detail_format,
                key_prefix="single_item",
                use_switcher=False,
            )
        else:
            # 複数行チェック時は「まとめタブ」＋「選択した各行ごとのタブ」を動的に生成
            tab_labels = ["📊 選択中まとめ"] + [
                f"📌 {i + 1}. {dest} × {item}" for i, (dest, item) in enumerate(selected_pairs)
            ]
            tabs = st.tabs(tab_labels)

            # 選択中まとめタブ（指定同時期／全期間スイッチャー付き）
            with tabs[0]:
                pair_mask_period = pd.Series(False, index=filtered_df.index)
                pair_mask_all = pd.Series(False, index=df.index)
                for dest, item in selected_pairs:
                    pair_mask_period |= (filtered_df["納品先名"] == dest) & (filtered_df["物品名"] == item)
                    pair_mask_all |= (df["納品先名"] == dest) & (df["物品名"] == item)

                combined_period_raw = filtered_df[pair_mask_period]
                combined_all_raw = df[pair_mask_all & (df["_date"] <= ref_date)]
                if selected_staffs:
                    combined_all_raw = combined_all_raw[combined_all_raw["担当者コード"].isin(selected_staffs)]

                combined_period_df = format_detail_df(combined_period_raw, include_pair_cols=True)
                combined_all_df = format_detail_df(combined_all_raw, include_pair_cols=True)

                ctrl_col, note_col = st.columns([1.4, 2.6])
                with ctrl_col:
                    summary_scope = st.segmented_control(
                        "表示する明細期間（まとめ）",
                        options=["指定同時期", "全期間（参考）"],
                        default="指定同時期",
                        key="summary_tab_scope",
                    )
                with note_col:
                    if summary_scope == "全期間（参考）":
                        st.caption("※ 選択中案件の同時期以外も含めた、基準日以前の全受注データです（担当者絞り込みがある場合は反映）。")
                    else:
                        st.caption("※ 選択中案件について、サイドバーで指定した「過去3年・同時期」に一致する明細です。")

                if summary_scope == "全期間（参考）":
                    target_combined_df = combined_all_df
                    sum_tag = "全期間"
                    sum_file_suffix = "全期間"
                else:
                    target_combined_df = combined_period_df
                    sum_tag = "同時期"
                    sum_file_suffix = "同時期"

                c_col1, c_col2, c_col3, c_col4 = st.columns(4)
                c_col1.metric("選択対象数", f"{len(selected_pairs):,} 件")
                c_col2.metric(f"{sum_tag} 明細合計行数", f"{len(target_combined_df):,} 行")
                c_col3.metric(f"{sum_tag} 売上合計", f"¥{int(target_combined_df['売上金額'].sum()):,}")
                c_col4.metric(f"{sum_tag} 粗利合計", f"¥{int(target_combined_df['粗利金額'].sum()):,}")

                st.dataframe(
                    target_combined_df.style.format(detail_format),
                    use_container_width=True,
                    hide_index=True,
                )

                st.download_button(
                    label=f"📥 選択中まとめ明細（{sum_tag}）をCSVダウンロード",
                    data=target_combined_df.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"受注明細_選択まとめ_{sum_file_suffix}_{ref_date.strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    key=f"dl_combined_detail_{sum_file_suffix}",
                )

            # チェックを付けた各行ごとの個別タブ
            for idx_tab, (sel_dest, sel_item) in enumerate(selected_pairs, start=1):
                with tabs[idx_tab]:
                    period_detail_raw = filtered_df[
                        (filtered_df["納品先名"] == sel_dest) & (filtered_df["物品名"] == sel_item)
                    ]
                    period_detail_df = format_detail_df(period_detail_raw)

                    all_detail_raw = df[
                        (df["納品先名"] == sel_dest)
                        & (df["物品名"] == sel_item)
                        & (df["_date"] <= ref_date)
                    ]
                    if selected_staffs:
                        all_detail_raw = all_detail_raw[all_detail_raw["担当者コード"].isin(selected_staffs)]
                    all_detail_df = format_detail_df(all_detail_raw)

                    render_single_item_detail(
                        period_detail_df=period_detail_df,
                        all_detail_df=all_detail_df,
                        sel_dest=sel_dest,
                        sel_item=sel_item,
                        detail_format=detail_format,
                        key_prefix=f"multi_item_{idx_tab}",
                        use_switcher=True,
                    )
