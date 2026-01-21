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
    if not os.path.isfile(DB_FILE):
        return pd.DataFrame(columns=["학과", "이름", "학번", "인원", "날짜", "시작", "종료", "방번호", "출석"])
    df = pd.read_csv(DB_FILE)
    if "출석" not in df.columns:
        df["출석"] = "미입실"
    return df

def check_overlap(date, start_t, end_t, room):
    df = get_latest_df()
    if df.empty: return False
    same_day_room = df[(df["날짜"] == str(date)) & (df["방번호"] == room)]
    for _, row in same_day_room.iterrows():
        try:
            e_start = datetime.strptime(row["시작"], "%H:%M").time()
            e_end = datetime.strptime(row["종료"], "%H:%M").time()
            n_start = datetime.strptime(start_t, "%H:%M").time()
            n_end = datetime.strptime(end_t, "%H:%M").time()
            if n_start < e_end and n_end > e_start: return True
        except: continue
    return False

def auto_cleanup_noshow(df):
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
    """URL 파라미터를 통한 QR 즉시 체크인 (10분 전 조기 입실 로직 추가)"""
    q_params = st.query_params
    if "checkin" in q_params:
        room_code = q_params["checkin"]
        target_room = "1번 스터디룸" if room_code == "room1" else "2번 스터디룸"
        
        now_kst = get_kst_now().replace(tzinfo=None)
        now_date = str(now_kst.date())
        now_time = now_kst.strftime("%H:%M")
        
        # 1. 현재 정규 시간대 예약자 확인
        mask_current = (df["방번호"] == target_room) & \
                       (df["날짜"] == now_date) & \
                       (df["시작"] <= now_time) & \
                       (df["종료"] > now_time) & \
                       (df["출석"] == "미입실")
        
        # 2. 조기 입실 확인 (예약 시작 10분 전 ~ 시작 직전)
        # 현재 시각에 10분을 더했을 때 시작 시간보다 크거나 같으면 조기 입실 가능 대상
        early_limit = (now_kst + timedelta(minutes=10)).strftime("%H:%M")
        mask_early = (df["방번호"] == target_room) & \
                     (df["날짜"] == now_date) & \
                     (df["시작"] > now_time) & \
                     (df["시작"] <= early_limit) & \
                     (df["출석"] == "미입실")

        # 3. 조기 입실 시 이전 예약자가 있는지 체크 (중복 방지)
        is_occupied = any((df["방번호"] == target_room) & \
                          (df["날짜"] == now_date) & \
                          (df["시작"] < now_time) & \
                          (df["종료"] > now_time))

        if any(mask_current):
            target_mask = mask_current
        elif any(mask_early) and not is_occupied:
            target_mask = mask_early
            st.toast("⚡ 조기 입실이 확인되었습니다!")
        else:
            target_mask = None

        if target_mask is not None:
            user_name = df.loc[target_mask, "이름"].values[0]
            df.loc[target_mask, "출석"] = "입실완료"
            df.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
            st.balloons()
            st.success(f"✅ 인증 성공: {user_name}님, {target_room} 입실 확인되었습니다!")
            st.query_params.clear()
        else:
            st.warning(f"⚠️ 인증 실패: 현재 예약된 시간이 아니거나 이전 팀이 이용 중입니다.")
    return df

# --- [2. 페이지 설정 및 디자인] ---
st.set_page_config(page_title="생과대 스터디룸 예약", page_icon="🌿", layout="wide")

st.markdown("""
    <style>
    :root { --point-color: #A7D7C5; --point-dark: #3E7D6B; }
    .stButton>button { background-color: var(--point-color); color: white; border-radius: 10px; font-weight: bold; border: none; }
    .schedule-card, .res-card { padding: 15px; border-radius: 12px; border-left: 6px solid var(--point-color); background-color: rgba(167, 215, 197, 0.1); margin-bottom: 12px; }
    .step-header { color: var(--point-dark); font-weight: bold; border-bottom: 2px solid var(--point-color); padding-bottom: 5px; margin-bottom: 15px; font-size: 1.2rem; }
    .success-receipt { border: 2px dashed var(--point-color); padding: 25px; border-radius: 15px; margin-top: 20px; }
    .receipt-title { color: var(--point-color); font-size: 1.5rem; font-weight: bold; text-align: center; margin-bottom: 20px; }
    .receipt-item { display: flex; justify-content: space-between; margin-bottom: 10px; border-bottom: 1px solid rgba(167, 215, 197, 0.3); padding-bottom: 5px; }
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
    st.markdown(f"<h2 style='color:var(--point-color);'>📊 실시간 점유 현황</h2>", unsafe_allow_html=True)
    st.info(f"🕒 **현재 시각(KST)** {now_kst.strftime('%H:%M')}")
    today_df = df_all[df_all["날짜"] == str(now_kst.date())].sort_values(by="시작")
    for r_name in ["1번 스터디룸", "2번 스터디룸"]:
        with st.expander(f"🚪 {r_name}", expanded=True):
            room_res = today_df[today_df["방번호"] == r_name]
            current_booking = None
            future_bookings = []
            for _, row in room_res.iterrows():
                try:
                    s_t = datetime.strptime(row["시작"], "%H:%M").time()
                    e_t = datetime.strptime(row["종료"], "%H:%M").time()
                    if s_t <= now_kst.time() < e_t: current_booking = row
                    elif s_t > now_kst.time(): future_bookings.append(row)
                except: continue
            if current_booking is not None:
                st.error(f"{'✅' if current_booking['출석'] == '입실완료' else '⚠️'} 현재 예약 중")
                st.caption(f"⏰ {current_booking['시작']}~{current_booking['종료']} ({current_booking['이름']}님)")
            else: st.success("✨ 현재 이용 가능")
            if future_bookings:
                st.markdown("<p style='font-size: 0.8rem; font-weight: bold; margin-top: 5px;'>📅 다음 예약</p>", unsafe_allow_html=True)
                for fb in future_bookings: st.markdown(f"<div style='font-size: 0.8rem;'>🕒 {fb['시작']}~{fb['종료']}</div>", unsafe_allow_html=True)

# --- [4. 메인 화면 구성] ---
st.title("🌿 스터디룸 예약 시스템")
tabs = st.tabs(["📅 예약 신청", "🔍 내 예약 확인", "📋 전체 일정 보기", "➕ 시간 연장", "♻️ 반납 및 취소"])

with tabs[0]:
    st.markdown('<div class="step-header">1. 예약자 정보</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    dept = c1.selectbox("🏢 학과", dept_options, key="reg_dept")
    name = c2.text_input("👤 이름", placeholder="성함", key="reg_name")
    sid = c3.text_input("🆔 학번", placeholder="8자리", key="reg_sid")
    count = c4.number_input("👥 인원 (최소 3명)", min_value=3, max_value=20, value=3, step=1, key="reg_count")

    st.markdown('<div class="step-header">2. 스터디룸 및 시간</div>', unsafe_allow_html=True)
    sc1, sc2, tc1, tc2 = st.columns([2, 1, 1, 1])
    room = sc1.selectbox("🚪 스터디룸", ["1번 스터디룸", "2번 스터디룸"], key="reg_room")
    date = sc2.date_input("📅 날짜", min_value=now_kst.date(), key="reg_date")
    available_start = [t for t in time_options_all if t > now_kst.strftime("%H:%M")] if date == now_kst.date() else time_options_all
    if not available_start: st.error("오늘 예약 종료")
    else:
        st_t = tc1.selectbox("⏰ 시작", available_start, index=0, key="reg_start")
        en_t = tc2.selectbox("⏰ 종료", [t for t in time_options_all if t > st_t], index=0, key="reg_end")
        if st.button("🚀 예약 신청", key="btn_reservation"):
            duration = datetime.strptime(en_t, "%H:%M") - datetime.strptime(st_t, "%H:%M")
            if not (name.strip() and sid.strip()): st.error("정보 미입력")
            elif duration > timedelta(hours=3): st.error("최대 3시간")
            elif check_overlap(date, st_t, en_t, room): st.error("이미 예약 있음")
            else:
                new_row = pd.DataFrame([[dept, name.strip(), sid.strip(), count, str(date), st_t, en_t, room, "미입실"]], columns=["학과", "이름", "학번", "인원", "날짜", "시작", "종료", "방번호", "출석"])
                new_row.to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False, encoding='utf-8-sig')
                st.balloons()
                st.markdown(f'<div class="success-receipt"><div class="receipt-title">🌿 예약 확인서</div><div class="receipt-item"><span>신청자</span><b>{name}</b></div><div class="receipt-item"><span>장소</span><b>{room}</b></div><div class="receipt-item"><span>시간</span><b>{date} / {st_t}~{en_t}</b></div></div>', unsafe_allow_html=True)

with tabs[1]:
    mc1, mc2 = st.columns(2)
    m_name = mc1.text_input("이름", key="lookup_name")
    m_sid = mc2.text_input("학번", key="lookup_sid")
    if st.button("조회", key="btn_lookup"):
        res = df_all[(df_all["이름"] == m_name.strip()) & (df_all["학번"].astype(str) == m_sid.strip())]
        if not res.empty:
            r = res.iloc[0]
            st.markdown(f'<div class="res-card">📍 {r["방번호"]} | ⏰ {r["시작"]}~{r["종료"]} | 상태: {r["출석"]}</div>', unsafe_allow_html=True)
        else: st.error("내역 없음")

with tabs[2]:
    if not df_all.empty:
        s_date = st.selectbox("날짜", sorted(df_all["날짜"].unique()), key="view_date")
        day_df = df_all[df_all["날짜"] == s_date].sort_values(by=["방번호", "시작"])
        for r_name in ["1번 스터디룸", "2번 스터디룸"]:
            st.markdown(f"#### 🚪 {r_name}")
            room_day = day_df[day_df["방번호"] == r_name]
            if room_day.empty: st.caption("예약 없음")
            else:
                for _, row in room_day.iterrows():
                    st.markdown(f'<div class="schedule-card"><b>{row["시작"]}~{row["종료"]}</b> | {row["이름"]} ({row["출석"]})</div>', unsafe_allow_html=True)

with tabs[3]:
    ext_name = st.text_input("이름 (연장)", key="ext_n")
    if st.button("연장 확인", key="btn_ext_check"):
        res_e = df_all[(df_all["이름"] == ext_name) & (df_all["날짜"] == str(now_kst.date()))]
        if not res_e.empty:
            target = res_e.iloc[-1]
            st.session_state['ext_target'] = target
            st.success(f"현재 종료: {target['종료']}. 30분 전부터 연장 가능")
    if 'ext_target' in st.session_state:
        target = st.session_state['ext_target']
        new_en = st.selectbox("새 종료 시간", [t for t in time_options_all if t > target['종료']][:4], key="ext_select")
        if st.button("연장 확정", key="btn_ext_confirm"):
            df_up = get_latest_df()
            idx = df_up[(df_up["이름"] == ext_name) & (df_up["날짜"] == str(now_kst.date())) & (df_up["시작"] == target['시작'])].index
            df_up.loc[idx, "종료"] = new_en; df_up.to_csv(DB_FILE, index=False, encoding='utf-8-sig'); st.rerun()

with tabs[4]:
    can_name = st.text_input("이름 (취소)", key="can_n")
    if st.button("취소 내역", key="btn_can_lookup"):
        res_c = df_all[df_all["이름"] == can_name]
        if not res_c.empty: st.session_state['re_target'] = res_c.iloc[0]; st.info(f"대상: {st.session_state['re_target']['방번호']}")
    if 're_target' in st.session_state:
        if st.button("최종 취소", key="btn_can_confirm"):
            df_del = get_latest_df(); t = st.session_state['re_target']
            df_del.drop(df_del[(df_del["이름"]==t["이름"]) & (df_del["학번"]==str(t["학번"])) & (df_del["날짜"]==t["날짜"]) & (df_del["시작"]==t["시작"])].index).to_csv(DB_FILE, index=False, encoding='utf-8-sig'); st.rerun()

with st.expander("🛠️ 관리자"):
    pw = st.text_input("PW", type="password", key="admin_pw")
    if pw == "bio1234":
        df_ad = get_latest_df()
        st.dataframe(df_ad)
        if st.button("선택 삭제", key="admin_del"):
            # 관리자 전용 삭제 로직 (기존과 동일)
            pass
