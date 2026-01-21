import streamlit as st
import pandas as pd
import os
import urllib.parse
from datetime import datetime, timedelta

# 데이터 저장 파일명
DB_FILE = "reservations.csv"

# 1. 페이지 설정 및 디자인
st.set_page_config(page_title="생과대 스터디룸 예약", page_icon="🌿", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f9fdfb; }
    .stButton>button { background-color: #A7D7C5; color: white; border-radius: 8px; width: 100%; font-weight: bold; }
    .step-header { color: #3E7D6B; font-weight: bold; border-bottom: 2px solid #A7D7C5; padding-bottom: 5px; margin-bottom: 15px; font-size: 1.2rem; }
    .notice-box { background-color: #e8f4f0; padding: 15px; border-radius: 10px; border: 1px solid #A7D7C5; margin-bottom: 20px; }
    .schedule-card { background-color: #ffffff; padding: 15px; border-radius: 12px; border-left: 8px solid #A7D7C5; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 12px; }
    .res-card { background-color: #ffffff; padding: 20px; border-radius: 12px; border-left: 6px solid #A7D7C5; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-top: 10px; }
    .spacer { margin-top: 60px; }
    </style>
    """, unsafe_allow_html=True)

# --- 핵심 로직 함수 ---

def get_latest_df():
    """항상 물리적 파일에서 최신 데이터를 읽어옵니다."""
    if not os.path.isfile(DB_FILE):
        return pd.DataFrame(columns=["학과", "이름", "학번", "인원", "날짜", "시작", "종료", "방번호", "출석"])
    df = pd.read_csv(DB_FILE)
    if "출석" not in df.columns:
        df["출석"] = "미입실"
    return df

def check_overlap(date, start_t, end_t, room):
    """시간 중복을 확인합니다."""
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
    """예약 시작 15분이 지났는데 미입실인 예약을 자동 삭제합니다."""
    now = datetime.now()
    now_date = str(now.date())
    to_delete = []
    for idx, row in df.iterrows():
        if row["날짜"] == now_date and row["출석"] == "미입실":
            try:
                start_dt = datetime.strptime(f"{row['날짜']} {row['시작']}", "%Y-%m-%d %H:%M")
                if now > (start_dt + timedelta(minutes=15)):
                    to_delete.append(idx)
            except: continue
    if to_delete:
        df = df.drop(to_delete)
        df.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
    return df

def process_qr_checkin(df):
    """URL 쿼리 파라미터를 읽어 즉시 체크인 처리합니다."""
    q_params = st.query_params
    if "checkin" in q_params:
        room_code = q_params["checkin"]
        target_room = "1번 스터디룸" if room_code == "room1" else "2번 스터디룸"
        now = datetime.now()
        now_date = str(now.date())
        now_time = now.strftime("%H:%M")
        mask = (df["방번호"] == target_room) & \
               (df["날짜"] == now_date) & \
               (df["시작"] <= now_time) & \
               (df["종료"] > now_time) & \
               (df["출석"] == "미입실")
        if any(mask):
            user_name = df.loc[mask, "이름"].values[0]
            df.loc[mask, "출석"] = "입실완료"
            df.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
            st.success(f"✅ 인증 성공: {user_name}님, {target_room} 입실 확인되었습니다!")
            st.query_params.clear()
        else:
            st.warning(f"현재 {target_room}에 등록된 본인의 예약 시간이 아니거나 이미 인증되었습니다.")
    return df

# --- 초기 데이터 로드 및 자동 관리 실행 ---
df_all = get_latest_df()
df_all = auto_cleanup_noshow(df_all)
df_all = process_qr_checkin(df_all)

# --- 공통 설정 및 시간 ---
all_times = [f"{h:02d}:{m:02d}" for h in range(0, 24) for m in (0, 30)]
dept_options = ["스마트팜과학과", "식품생명공학과", "유전생명공학과", "융합바이오·신소재공학과"]
now = datetime.now()

# --- 사이드바: 실시간 현황판 ---
with st.sidebar:
    st.markdown("<h2 style='color:#3E7D6B;'>📊 실시간 점유 현황</h2>", unsafe_allow_html=True)
    today_df = df_all[df_all["날짜"] == str(now.date())].sort_values(by="시작")
    for r in ["1번 스터디룸", "2번 스터디룸"]:
        with st.expander(f"🚪 {r}", expanded=True):
            room_res = today_df[today_df["방번호"] == r]
            is_occ = False
            for _, row in room_res.iterrows():
                try:
                    s_t = datetime.strptime(row["시작"], "%H:%M").time()
                    e_t = datetime.strptime(row["종료"], "%H:%M").time()
                    if s_t <= now.time() < e_t:
                        is_occ = True
                        status = "✅ 입실완료" if row["출석"] == "입실완료" else "⚠️ 미인증(곧 자동취소)"
                        st.error(f"{status} ({row['시작']}~{row['종료']})")
                        break
                except: continue
            if not is_occ: st.success("✅ 예약 가능")
    st.divider()
    st.caption("🌿 생명과학대학 학생회")

# --- 메인 화면 ---
st.title("🌿 생명과학대학 스터디룸 예약 시스템")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📅 예약 신청", "🔍 내 예약 확인", "📋 전체 일정 보기", "➕ 시간 연장", "♻️ 반납 및 취소"])

# [탭 1: 예약 신청]
with tab1:
    st.markdown('<div class="step-header">1. 예약 날짜 및 스터디룸 선택</div>', unsafe_allow_html=True)
    sc1, sc2 = st.columns(2)
    date = sc1.date_input("📅 날짜", min_value=now.date(), max_value=now.date()+timedelta(days=13), key="reg_date")
    room = sc2.selectbox("🚪 스터디룸 선택", ["1번 스터디룸", "2번 스터디룸"], key="reg_room")

    # --- 실시간 시간 필터링 및 추천 로직 ---
    current_hm = now.strftime("%H:%M")
    if date == now.date():
        # 오늘이면 현재 시간 이후의 옵션만 보여줌 (지난 시간 예약 방지)
        available_start_times = [t for t in all_times if t > current_hm]
    else:
        available_start_times = all_times

    if not available_start_times:
        st.error("⚠️ 오늘은 더 이상 예약 가능한 시간대가 없습니다.")
    else:
        st.markdown('<div class="step-header">2. 시간 및 이용자 정보 입력</div>', unsafe_allow_html=True)
        tc1, tc2, tc3 = st.columns([1, 1, 2])
        
        # 시작 시간: 가장 가까운 시간이 자동으로 첫 번째(index=0)로 선택됨
        st_t = tc1.selectbox("⏰ 시작", available_start_times, index=0, key="reg_start")
        
        # 종료 시간: 시작 시간 이후의 옵션만 필터링
        available_end_times = [t for t in all_times if t > st_t]
        en_t = tc2.selectbox("⏰ 종료", available_end_times, index=0, key="reg_end")
        
        count = tc3.number_input("👥 인원 (최소 3명)", min_value=1, max_value=20, value=3, key="reg_count")

        st.markdown('<div class="step-header">3. 신청자 상세 정보</div>', unsafe_allow_html=True)
        inf1, inf2, inf3 = st.columns(3)
        dept = inf1.selectbox("🏢 학과", dept_options, key="reg_dept")
        name = inf2.text_input("👤 이름", placeholder="성함 입력", key="reg_name")
        sid = inf3.text_input("🆔 학번", placeholder="학번 8자리", key="reg_sid")

        if st.button("🚀 예약 신청하기"):
            if not (name.strip() and sid.strip()): 
                st.error("이름과 학번을 모두 입력해 주세요.")
            elif count < 3:
                st.error("🚫 스터디룸 이용 최소 인원은 3명입니다.")
            elif any((df_all["이름"] == name.strip()) & (df_all["학번"] == str(sid.strip()))): 
                st.error("🚫 이미 등록된 예약이 존재합니다. (1인 1예약 원칙)")
            elif check_overlap(date, st_t, en_t, room): 
                st.error("❌ 선택한 시간에 이미 예약이 존재합니다.")
            else:
                new_data = pd.DataFrame([[dept, name.strip(), sid.strip(), count, str(date), st_t, en_t, room, "미입실"]], 
                                         columns=["학과", "이름", "학번", "인원", "날짜", "시작", "종료", "방번호", "출석"])
                new_data.to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False, encoding='utf-8-sig')
                st.success(f"🎉 예약 완료! {name}님, 15분 내에 입실 확인(QR)을 완료해 주세요.")
                st.rerun()

# [탭 2: 내 예약 확인]
with tab2:
    st.markdown('<div class="step-header">🔍 예약 확인</div>', unsafe_allow_html=True)
    mc1, mc2 = st.columns(2)
    m_name = mc1.text_input("조회용 이름", key="my_name")
    m_sid = mc2.text_input("조회용 학번", key="my_sid")
    if st.button("조회하기"):
        res = df_all[(df_all["이름"].astype(str).str.strip() == m_name.strip()) & (df_all["학번"].astype(str).str.strip() == m_sid.strip())]
        if not res.empty:
            r = res.iloc[0]
            st.markdown(f"""<div class="res-card"><h3>✅ {r['이름']}님의 예약</h3><p>📍 {r['방번호']} / 📅 {r['날짜']} / ⏰ {r['시작']} ~ {r['종료']}</p><p>상태: <b>{r['출석']}</b></p></div>""", unsafe_allow_html=True)
        else: st.error("내역이 없습니다.")

# [탭 3: 전체 일정]
with tab3:
    st.markdown('<div class="step-header">📋 통합 예약 일정</div>', unsafe_allow_html=True)
    if not df_all.empty:
        u_dates = sorted(df_all["날짜"].unique())
        s_date = st.selectbox("날짜 선택", u_dates)
        day_df = df_all[df_all["날짜"] == s_date].sort_values(by="시작")
        c1, c2 = st.columns(2)
        for r_name, col in zip(["1번 스터디룸", "2번 스터디룸"], [c1, c2]):
            with col:
                st.markdown(f"**[{r_name}]**")
                r_df = day_df[day_df["방번호"] == r_name]
                if r_df.empty: st.caption("예약 없음")
                else:
                    for _, row in r_df.iterrows():
                        st.markdown(f'<div class="schedule-card">{row["시작"]}~{row["종료"]} | {row["이름"]} ({row["출석"]})</div>', unsafe_allow_html=True)

# [탭 4: 시간 연장]
with tab4:
    st.markdown('<div class="step-header">➕ 이용 시간 연장</div>', unsafe_allow_html=True)
    e_name = st.text_input("이름 (연장용)", key="e_n")
    if st.button("연장 가능 여부 확인"):
        df_e = get_latest_df()
        res_e = df_e[(df_e["이름"] == e_name) & (df_e["날짜"] == str(now.date()))]
        if not res_e.empty:
            target = res_e.iloc[-1]
            try:
                end_dt = datetime.combine(now.date(), datetime.strptime(target['종료'], "%H:%M").time())
                if (end_dt - timedelta(minutes=30)) <= now < end_dt:
                    st.session_state['ext_target'] = target
                    st.success(f"연장 가능! 현재 종료 시간: {target['종료']}")
                else: st.warning("종료 30분 전부터 종료 시각까지만 연장이 가능합니다.")
            except: pass
        else: st.warning("오늘 이용 중인 내역이 없습니다.")
    if 'ext_target' in st.session_state:
        target = st.session_state['ext_target']
        new_en = st.selectbox("새 종료 시간", [t for t in all_times if t > target['종료']][:4])
        if st.button("연장 확정"):
            if check_overlap(now.date(), target['종료'], new_en, target['방번호']): st.error("다음 예약과 시간이 겹칩니다.")
            else:
                df_up = get_latest_df()
                idx = df_up[(df_up["이름"] == e_name) & (df_up["날짜"] == str(now.date())) & (df_up["시작"] == target['시작'])].index
                df_up.loc[idx, "종료"] = new_en
                df_up.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
                st.success("연장 완료!"); del st.session_state['ext_target']; st.rerun()

# [탭 5: 반납 및 취소]
with tab5:
    st.markdown('<div class="step-header">♻️ 예약 반납 및 취소</div>', unsafe_allow_html=True)
    c_name = st.text_input("이름 (취소용)", key="c_n")
    if st.button("취소 내역 확인"):
        df_c = get_latest_df()
        res_c = df_c[df_c["이름"] == c_name].sort_values(by="날짜")
        if not res_c.empty:
            st.session_state['re_target'] = res_c.iloc[0]
            t = st.session_state['re_target']
            st.info(f"선택된 예약: {t['날짜']} / {t['방번호']} ({t['시작']}~{t['종료']})")
    if 're_target' in st.session_state:
        if st.button("✅ 최종 취소/반납 수행", type="primary"):
            df_del = get_latest_df()
            t = st.session_state['re_target']
            df_del.drop(df_del[(df_del["이름"]==t["이름"]) & (df_del["학번"]==str(t["학번"])) & (df_del["날짜"]==t["날짜"]) & (df_del["시작"]==t["시작"])].index).to_csv(DB_FILE, index=False, encoding='utf-8-sig')
            st.success("성공적으로 취소되었습니다."); del st.session_state['re_target']; st.rerun()

# --- 관리자 메뉴 ---
st.markdown('<div class="spacer"></div>', unsafe_allow_html=True)
with st.expander("🛠️ 관리자 전용 메뉴"):
    pw = st.text_input("Admin Password", type="password")
    if pw == "bio1234":
        df_admin = get_latest_df()
        st.dataframe(df_admin, use_container_width=True)
        csv = df_admin.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
        st.download_button("📥 데이터 다운로드 (CSV)", data=csv, file_name="reservations_backup.csv", mime="text/csv")
