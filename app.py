import streamlit as st
import pandas as pd
import os
import urllib.parse
from datetime import datetime, timedelta, timezone

# 데이터 저장 파일명
DB_FILE = "reservations.csv"

# --- [1. 핵심 함수 정의] ---

def get_kst_now():
    """서버 시간(UTC)을 한국 시간(KST)으로 변환합니다."""
    return datetime.now(timezone.utc) + timedelta(hours=9)

def get_latest_df():
    """최신 데이터를 읽어옵니다."""
    if not os.path.isfile(DB_FILE):
        return pd.DataFrame(columns=["학과", "이름", "학번", "인원", "날짜", "시작", "종료", "방번호", "출석"])
    df = pd.read_csv(DB_FILE)
    if "출석" not in df.columns:
        df["출석"] = "미입실"
    # 학번 데이터를 문자열로 통일하여 매칭 오류 방지
    df["학번"] = df["학번"].astype(str)
    return df

def is_already_booked(rep_name, rep_id):
    """중복 예약 확인 (1인 1예약 원칙)"""
    df = get_latest_df()
    if df.empty: return False
    duplicate = df[(df["이름"].astype(str).str.strip() == str(rep_name).strip()) & 
                   (df["학번"].astype(str).str.strip() == str(rep_id).strip())]
    return not duplicate.empty

def check_overlap(date, start_t, end_t, room):
    """시간 중복 확인"""
    df = get_latest_df()
    if df.empty: return False
    same_day_room = df[(df["날짜"] == str(date)) & (df["방번호"] == room)]
    for _, row in same_day_room.iterrows():
        try:
            fmt = "%H:%M"
            e_start = datetime.strptime(row["시작"], fmt).time()
            e_end = datetime.strptime(row["종료"], fmt).time()
            n_start = datetime.strptime(start_t, fmt).time()
            n_end = datetime.strptime(end_t, fmt).time()
            if n_start < e_end and n_end > e_start: return True
        except: continue
    return False

def auto_cleanup_noshow(df):
    """예약 시작 15분 후까지 미입실 시 자동 삭제"""
    now_kst = get_kst_now().replace(tzinfo=None)
    now_date = str(now_kst.date())
    to_delete = []
    for idx, row in df.iterrows():
        if row["날짜"] == now_date and row["출석"] == "미입실":
            try:
                start_dt = datetime.strptime(f"{row['날짜']} {row['시작']}", "%Y-%m-%d %H:%M")
                if now_kst > (start_dt + timedelta(minutes=15)):
                    to_delete.append(idx)
            except: continue
    if to_delete:
        df = df.drop(to_delete)
        df.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
    return df

def process_qr_checkin(df):
    """QR 즉시 체크인 및 조기 입실(10분 전) 로직"""
    q_params = st.query_params
    if "checkin" in q_params:
        room_code = q_params["checkin"]
        target_room = "1번 스터디룸" if room_code == "room1" else "2번 스터디룸"
        now_kst = get_kst_now().replace(tzinfo=None)
        now_date = str(now_kst.date())
        now_time = now_kst.strftime("%H:%M")
        
        # 정규 시간 및 10분 전 조기입실 매칭
        early_limit = (now_kst + timedelta(minutes=10)).strftime("%H:%M")
        mask = (df["방번호"] == target_room) & (df["날짜"] == now_date) & \
               (df["시작"] <= early_limit) & (df["종료"] > now_time) & (df["출석"] == "미입실")
        
        if any(mask):
            user_name = df.loc[mask, "이름"].values[0]
            df.loc[mask, "출석"] = "입실완료"
            df.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
            st.balloons()
            st.success(f"✅ 인증 성공: {user_name}님, 입실 확인되었습니다!")
            st.query_params.clear()
        else:
            st.warning("⚠️ 인증 실패: 예약 시간이 아니거나 이미 인증되었습니다.")
    return df

# --- [2. 디자인 및 초기 설정] ---
st.set_page_config(page_title="생과대 스터디룸 예약", page_icon="🌿", layout="wide")

st.markdown("""
    <style>
    :root { --point-color: #A7D7C5; --point-dark: #3E7D6B; }
    .stButton>button { background-color: var(--point-color); color: white; border-radius: 10px; font-weight: bold; border: none; width: 100%; }
    .schedule-card, .res-card { padding: 15px; border-radius: 12px; border-left: 6px solid var(--point-color); background-color: rgba(167, 215, 197, 0.1); margin-bottom: 12px; }
    .step-header { color: var(--point-dark); font-weight: bold; border-bottom: 2px solid var(--point-color); padding-bottom: 5px; margin-bottom: 15px; font-size: 1.2rem; }
    </style>
    """, unsafe_allow_html=True)

now_kst = get_kst_now().replace(tzinfo=None)
time_options_all = [f"{h:02d}:{m:02d}" for h in range(0, 24) for m in (0, 30)]
dept_options = ["스마트팜과학과", "식품생명공학과", "유전생명공학과", "융합바이오·신소재공학과"]

df_all = get_latest_df()
df_all = auto_cleanup_noshow(df_all)
df_all = process_qr_checkin(df_all)

# --- [3. 사이드바 현황판] ---
with st.sidebar:
    st.markdown(f"<h2 style='color:var(--point-color);'>📊 실시간 현황</h2>", unsafe_allow_html=True)
    st.info(f"🕒 **현재 시각** {now_kst.strftime('%H:%M')}")
    today_df = df_all[df_all["날짜"] == str(now_kst.date())].sort_values(by="시작")
    for r in ["1번 스터디룸", "2번 스터디룸"]:
        with st.expander(f"🚪 {r}", expanded=True):
            room_res = today_df[today_df["방번호"] == r]
            occ = room_res[(room_res["시작"] <= now_kst.strftime("%H:%M")) & (room_res["종료"] > now_kst.strftime("%H:%M"))]
            if not occ.empty:
                st.error(f"⚠️ 사용 중 ({occ.iloc[0]['이름']}님)")
            else: st.success("✨ 이용 가능")

# --- [4. 메인 화면] ---
st.title("🌿 스터디룸 예약 시스템")
tabs = st.tabs(["📅 예약 신청", "🔍 내 예약 확인", "📋 전체 일정", "➕ 시간 연장", "♻️ 반납 및 취소"])

with tabs[0]:
    st.markdown('<div class="step-header">1. 정보 입력</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    dept = c1.selectbox("🏢 학과", dept_options, key="reg_dept")
    name = c2.text_input("👤 이름", placeholder="성함", key="reg_name")
    sid = c3.text_input("🆔 학번", placeholder="8자리", key="reg_sid")
    count = c4.number_input("👥 인원 (최소 3명)", min_value=3, max_value=20, value=3, key="reg_count")

    sc1, sc2, tc1, tc2 = st.columns([2, 1, 1, 1])
    room = sc1.selectbox("🚪 장소", ["1번 스터디룸", "2번 스터디룸"], key="reg_room")
    date = sc2.date_input("📅 날짜", min_value=now_kst.date(), key="reg_date")
    
    available_start = [t for t in time_options_all if t > now_kst.strftime("%H:%M")] if date == now_kst.date() else time_options_all
    if not available_start: st.error("오늘 예약 종료")
    else:
        st_t = tc1.selectbox("⏰ 시작", available_start, index=0, key="reg_start")
        en_t = tc2.selectbox("⏰ 종료", [t for t in time_options_all if t > st_t], index=0, key="reg_end")
        if st.button("🚀 예약 신청", key="btn_reservation"):
            duration = datetime.strptime(en_t, "%H:%M") - datetime.strptime(st_t, "%H:%M")
            if not (name.strip() and sid.strip()): st.error("정보 미입력")
            elif is_already_booked(name, sid): st.error("🚫 이미 예약 내역이 존재합니다.")
            elif duration > timedelta(hours=3): st.error("🚫 최대 3시간 예약 가능")
            elif check_overlap(date, st_t, en_t, room): st.error("❌ 이미 예약된 시간")
            else:
                new_row = pd.DataFrame([[dept, name.strip(), sid.strip(), count, str(date), st_t, en_t, room, "미입실"]], columns=["학과", "이름", "학번", "인원", "날짜", "시작", "종료", "방번호", "출석"])
                new_row.to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False, encoding='utf-8-sig')
                st.success("예약 완료!"); st.rerun()

with tabs[1]:
    mc1, mc2 = st.columns(2)
    m_name = mc1.text_input("이름", key="lookup_name")
    m_sid = mc2.text_input("학번", key="lookup_sid")
    if st.button("조회", key="btn_lookup"):
        df_l = get_latest_df()
        res = df_l[(df_l["이름"] == m_name.strip()) & (df_l["학번"] == m_sid.strip())]
        if not res.empty:
            for _, r in res.iterrows():
                st.markdown(f'<div class="res-card">📍 {r["방번호"]} | ⏰ {r["시작"]}~{r["종료"]} ({r["날짜"]}) | 상태: {r["출석"]}</div>', unsafe_allow_html=True)
        else: st.error("내역 없음")

with tabs[2]:
    df_v = get_latest_df()
    if not df_v.empty:
        s_date = st.selectbox("날짜", sorted(df_v["날짜"].unique()), key="view_date")
        day_df = df_v[df_v["날짜"] == s_date].sort_values(by=["방번호", "시작"])
        for r_name in ["1번 스터디룸", "2번 스터디룸"]:
            st.markdown(f"#### 🚪 {r_name}")
            room_day = day_df[day_df["방번호"] == r_name]
            if room_day.empty: st.caption("예약 없음")
            else:
                for _, row in room_day.iterrows():
                    st.markdown(f'<div class="schedule-card"><b>{row["시작"]}~{row["종료"]}</b> | {row["이름"]} ({row["출석"]})</div>', unsafe_allow_html=True)
    else: st.info("예약 없음")

with tabs[3]:
    ext_n = st.text_input("대표자 이름 (연장)", key="ext_n")
    ext_id = st.text_input("학번 (연장)", key="ext_id")
    if st.button("연장 가능 조회", key="btn_ext_check"):
        df_e = get_latest_df()
        res_e = df_e[(df_e["이름"] == ext_n.strip()) & (df_e["학번"] == ext_id.strip()) & (df_e["날짜"] == str(now_kst.date()))]
        if not res_e.empty:
            st.session_state['ext_target'] = res_e.iloc[-1]
            st.success(f"현재 종료: {st.session_state['ext_target']['종료']}. 연장 가능!")
    if 'ext_target' in st.session_state:
        new_en = st.selectbox("새 종료 시간", [t for t in time_options_all if t > st.session_state['ext_target']['종료']][:4], key="ext_sel")
        if st.button("연장 확정", key="btn_ext_confirm"):
            df_up = get_latest_df()
            idx = df_up[(df_up["이름"] == ext_n.strip()) & (df_up["학번"] == ext_id.strip()) & (df_up["시작"] == st.session_state['ext_target']['시작'])].index
            df_up.loc[idx, "종료"] = new_en; df_up.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
            st.success("연장 완료!"); del st.session_state['ext_target']; st.rerun()

with tabs[4]:
    st.markdown('<div class="step-header">♻️ 본인 확인 후 취소</div>', unsafe_allow_html=True)
    can_n = st.text_input("대표자 이름 (취소)", key="can_n")
    can_id = st.text_input("학번 (취소)", key="can_id")
    if st.button("예약 조회", key="btn_can_lookup"):
        df_c = get_latest_df()
        # 이름과 학번이 모두 일치하는 예약만 검색
        res_c = df_c[(df_c["이름"] == can_n.strip()) & (df_c["학번"] == can_id.strip())].sort_values(by="날짜")
        if not res_c.empty:
            st.session_state['cancel_list'] = res_c
        else: st.error("일치하는 예약 내역이 없습니다.")

    if 'cancel_list' in st.session_state:
        # 삭제할 대상을 선택 (여러 개 예약했을 경우 대비)
        options = [f"{r['날짜']} | {r['방번호']} ({r['시작']}~{r['종료']})" for _, r in st.session_state['cancel_list'].iterrows()]
        target_idx = st.selectbox("취소할 예약을 선택하세요", range(len(options)), format_func=lambda x: options[x])
        
        if st.button("✅ 선택한 예약 취소하기", type="primary", key="btn_can_confirm"):
            df_del = get_latest_df()
            t = st.session_state['cancel_list'].iloc[target_idx]
            # 정확한 행 매칭 후 삭제
            df_del = df_del.drop(df_del[(df_del["이름"] == t["이름"]) & 
                                       (df_del["학번"] == t["학번"]) & 
                                       (df_del["날짜"] == t["날짜"]) & 
                                       (df_del["시작"] == t["시작"])].index)
            df_del.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
            st.success("취소가 성공적으로 처리되었습니다.")
            # 상태 초기화 및 새로고침
            if 'cancel_list' in st.session_state: del st.session_state['cancel_list']
            st.rerun()

with st.expander("🛠️ 관리자 메뉴"):
    pw = st.text_input("비밀번호", type="password", key="admin_pw")
    if pw == "bio1234":
        df_ad = get_latest_df()
        if not df_ad.empty:
            st.markdown("### 🗑️ 강제 삭제")
            labels = [f"{r['이름']} | {r['날짜']} | {r['시작']} ({r['방번호']})" for _, r in df_ad.iterrows()]
            sel_idx = st.selectbox("삭제 대상 선택", range(len(labels)), format_func=lambda x: labels[x])
            if st.button("강제 삭제 실행", key="btn_admin_del"):
                t = df_ad.iloc[sel_idx]
                df_ad = df_ad.drop(df_ad[(df_ad["이름"] == t["이름"]) & (df_ad["학번"] == t["학번"]) & (df_ad["날짜"] == t["날짜"]) & (df_ad["시작"] == t["시작"])].index)
                df_ad.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
                st.rerun()
            st.dataframe(df_ad)
