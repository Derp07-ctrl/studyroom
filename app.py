import streamlit as st
import pandas as pd
import os
import urllib.parse
from datetime import datetime, timedelta, timezone

# 데이터 저장 파일명
DB_FILE = "reservations.csv"

# --- [1. 핵심 함수 정의] 배포 에러 방지를 위해 최상단 배치 ---

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
    q_params = st.query_params
    if "checkin" in q_params:
        room_code = q_params["checkin"]
        target_room = "1번 스터디룸" if room_code == "room1" else "2번 스터디룸"
        now_kst = get_kst_now().replace(tzinfo=None)
        now_date = str(now_kst.date())
        now_time = now_kst.strftime("%H:%M")
        mask = (df["방번호"] == target_room) & (df["날짜"] == now_date) & \
               (df["시작"] <= now_time) & (df["종료"] > now_time) & (df["출석"] == "미입실")
        if any(mask):
            user_name = df.loc[mask, "이름"].values[0]
            df.loc[mask, "출석"] = "입실완료"
            df.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
            st.success(f"✅ 인증 성공: {user_name}님, {target_room} 입실 확인되었습니다!")
            st.query_params.clear()
        else:
            st.warning(f"현재 {target_room}에 등록된 본인의 예약 시간이 아니거나 이미 인증되었습니다.")
    return df

# --- [2. 페이지 설정 및 디자인 틀 유지] ---
st.set_page_config(page_title="생과대 스터디룸 예약", page_icon="🌿", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f9fdfb; }
    .stButton>button { background-color: #A7D7C5; color: white; border-radius: 8px; width: 100%; font-weight: bold; }
    .step-header { color: #3E7D6B; font-weight: bold; border-bottom: 2px solid #A7D7C5; padding-bottom: 5px; margin-bottom: 15px; font-size: 1.2rem; }
    .schedule-card { background-color: #ffffff; padding: 15px; border-radius: 12px; border-left: 8px solid #A7D7C5; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 12px; }
    .res-card { background-color: #ffffff; padding: 20px; border-radius: 12px; border-left: 6px solid #A7D7C5; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-top: 10px; }
    .spacer { margin-top: 60px; }
    </style>
    """, unsafe_allow_html=True)

# 한국 시간 기준으로 변수 설정
now_kst = get_kst_now().replace(tzinfo=None)
time_options_all = [f"{h:02d}:{m:02d}" for h in range(0, 24) for m in (0, 30)]
dept_options = ["스마트팜과학과", "식품생명공학과", "유전생명공학과", "융합바이오·신소재공학과"]

df_all = get_latest_df()
df_all = auto_cleanup_noshow(df_all)
df_all = process_qr_checkin(df_all)

# --- [3. 사이드바 실시간 현황] ---
with st.sidebar:
    st.markdown("<h2 style='color:#3E7D6B;'>📊 실시간 점유 현황</h2>", unsafe_allow_html=True)
    today_df = df_all[df_all["날짜"] == str(now_kst.date())].sort_values(by="시작")
    for r in ["1번 스터디룸", "2번 스터디룸"]:
        with st.expander(f"🚪 {r}", expanded=True):
            room_res = today_df[today_df["방번호"] == r]
            is_occ = False
            for _, row in room_res.iterrows():
                try:
                    s_t = datetime.strptime(row["시작"], "%H:%M").time()
                    e_t = datetime.strptime(row["종료"], "%H:%M").time()
                    if s_t <= now_kst.time() < e_t:
                        is_occ = True
                        status = "✅ 입실완료" if row["출석"] == "입실완료" else "⚠️ 미인증(곧 취소)"
                        st.error(f"{status} ({row['시작']}~{row['종료']})")
                        break
                except: continue
            if not is_occ: st.success("✅ 예약 가능")
    st.divider()
    st.caption("🌿 생명과학대학 학생회")

# --- [4. 메인 화면 구성] ---
st.title("🌿 생명과학대학 스터디룸 예약 시스템")

tabs = st.tabs(["📅 예약 신청", "🔍 내 예약 확인", "📋 전체 일정 보기", "➕ 시간 연장", "♻️ 반납 및 취소"])

# [탭 1: 예약 신청]
with tabs[0]:
    st.markdown('<div class="step-header">1. 예약자 정보 입력</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    dept = c1.selectbox("🏢 학과", dept_options, key="reg_dept")
    name = c2.text_input("👤 이름", placeholder="성함 입력", key="reg_name")
    sid = c3.text_input("🆔 학번", placeholder="학번 8자리", key="reg_sid")
    # 최소 인원 3명 제한
    count = c4.number_input("👥 인원 (최소 3명)", min_value=3, max_value=20, value=3, step=1, key="reg_count")

    st.markdown('<div class="step-header">2. 스터디룸 및 시간 선택</div>', unsafe_allow_html=True)
    sc1, sc2, tc1, tc2 = st.columns([2, 1, 1, 1])
    room = sc1.selectbox("🚪 스터디룸 선택", ["1번 스터디룸", "2번 스터디룸"], key="reg_room")
    date = sc2.date_input("📅 날짜", min_value=now_kst.date(), max_value=now_kst.date()+timedelta(days=13), key="reg_date")

    # 한국 시간 기준 지난 시간 필터링 및 자동 추천
    if date == now_kst.date():
        current_time_str = now_kst.strftime("%H:%M")
        available_start_times = [t for t in time_options_all if t > current_time_str]
    else:
        available_start_times = time_options_all

    if not available_start_times:
        st.error("⚠️ 오늘은 더 이상 예약 가능한 시간이 없습니다.")
    else:
        st_t = tc1.selectbox("⏰ 시작", available_start_times, index=0, key="reg_start")
        end_options = [t for t in time_options_all if t > st_t]
        en_t = tc2.selectbox("⏰ 종료", end_options, index=min(1, len(end_options)-1), key="reg_end")

        if st.button("🚀 예약 신청하기", key="btn_reservation"):
            t_fmt = "%H:%M"
            duration = datetime.strptime(en_t, t_fmt) - datetime.strptime(st_t, t_fmt)
            if not (name.strip() and sid.strip()): st.error("정보를 모두 입력해 주세요.")
            elif duration > timedelta(hours=3): st.error("🚫 최대 이용 가능 시간은 3시간입니다.")
            elif check_overlap(date, st_t, en_t, room): st.error("❌ 이미 예약된 시간입니다.")
            else:
                new_row = pd.DataFrame([[dept, name.strip(), sid.strip(), count, str(date), st_t, en_t, room, "미입실"]], columns=["학과", "이름", "학번", "인원", "날짜", "시작", "종료", "방번호", "출석"])
                new_row.to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False, encoding='utf-8-sig')
                st.success(f"🎉 예약 완료! {st_t} ~ {en_t}")
                st.rerun()

# [탭 2: 내 예약 확인]
with tabs[1]:
    st.markdown('<div class="step-header">🔍 예약 확인</div>', unsafe_allow_html=True)
    mc1, mc2 = st.columns(2)
    m_name = mc1.text_input("조회용 이름", key="my_name")
    m_sid = mc2.text_input("조회용 학번", key="my_sid")
    if st.button("조회", key="btn_lookup"):
        res = df_all[(df_all["이름"] == m_name.strip()) & (df_all["학번"].astype(str) == m_sid.strip())]
        if not res.empty:
            r = res.iloc[0]
            st.markdown(f"""<div class="res-card"><h3>✅ {r['이름']}님의 예약</h3><p>📍 {r['방번호']} / 📅 {r['날짜']} / ⏰ {r['시작']} ~ {r['종료']}</p><p>상태: <b>{r['출석']}</b></p></div>""", unsafe_allow_html=True)
        else: st.error("내역이 없습니다.")

# [탭 3: 전체 일정 보기]
with tabs[2]:
    st.markdown('<div class="step-header">📋 통합 예약 일정</div>', unsafe_allow_html=True)
    if not df_all.empty:
        u_dates = sorted(df_all["날짜"].unique())
        s_date = st.selectbox("날짜 선택", u_dates, key="view_date")
        day_df = df_all[df_all["날짜"] == s_date].sort_values(by="시작")
        st.dataframe(day_df[["방번호", "시작", "종료", "이름", "출석"]], use_container_width=True)

# [탭 4: 시간 연장]
with tabs[3]:
    st.markdown('<div class="step-header">➕ 이용 시간 연장</div>', unsafe_allow_html=True)
    ext_name = st.text_input("이름 (연장용)", key="ext_n")
    if st.button("연장 가능 여부 확인", key="btn_ext_check"):
        df_e = get_latest_df()
        res_e = df_e[(df_e["이름"] == ext_name) & (df_e["날짜"] == str(now_kst.date()))]
        if not res_e.empty:
            target = res_e.iloc[-1]
            end_dt = datetime.combine(now_kst.date(), datetime.strptime(target['종료'], "%H:%M").time())
            if (end_dt - timedelta(minutes=30)) <= now_kst < end_dt:
                st.session_state['ext_target'] = target
                st.success(f"현재 종료: {target['종료']}. 연장 가능!")
            else: st.warning("종료 30분 전부터 가능합니다.")
        else: st.error("오늘 예약 내역 없음")
    if 'ext_target' in st.session_state:
        target = st.session_state['ext_target']
        new_en = st.selectbox("새 종료 시간", [t for t in time_options_all if t > target['종료']][:4], key="ext_select")
        if st.button("연장 확정", key="btn_ext_confirm"):
            if check_overlap(now_kst.date(), target['종료'], new_en, target['방번호']): st.error("중복 발생")
            else:
                df_up = get_latest_df()
                idx = df_up[(df_up["이름"] == ext_name) & (df_up["날짜"] == str(now_kst.date())) & (df_up["시작"] == target['시작'])].index
                df_up.loc[idx, "종료"] = new_en; df_up.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
                st.success("연장 완료!"); del st.session_state['ext_target']; st.rerun()

# [탭 5: 반납 및 취소]
with tabs[4]:
    st.markdown('<div class="step-header">♻️ 예약 반납 및 취소</div>', unsafe_allow_html=True)
    can_name = st.text_input("이름 (취소용)", key="can_n")
    if st.button("조회하기", key="btn_can_lookup"):
        res_c = df_all[df_all["이름"] == can_name].sort_values(by="날짜")
        if not res_c.empty:
            st.session_state['re_target'] = res_c.iloc[0]
            st.info(f"선택: {st.session_state['re_target']['날짜']} {st.session_state['re_target']['방번호']}")
    if 're_target' in st.session_state:
        if st.button("✅ 최종 취소/반납", type="primary", key="btn_can_confirm"):
            df_del = get_latest_df(); t = st.session_state['re_target']
            df_del.drop(df_del[(df_del["이름"]==t["이름"]) & (df_del["학번"]==str(t["학번"])) & (df_del["날짜"]==t["날짜"]) & (df_del["시작"]==t["시작"])].index).to_csv(DB_FILE, index=False, encoding='utf-8-sig')
            st.success("완료"); del st.session_state['re_target']; st.rerun()

# --- 관리자 메뉴 ---
st.markdown('<div class="spacer"></div>', unsafe_allow_html=True)
with st.expander("🛠️ 관리자 전용 메뉴"):
    pw = st.text_input("Admin Password", type="password", key="admin_pw")
    if pw == "bio1234":
        df_ad = get_latest_df()
        if not df_ad.empty:
            df_ad['label'] = df_ad['이름'] + " | " + df_ad['날짜'] + " | " + df_ad['시작'] + " (" + df_ad['방번호'] + ")"
            target_l = st.selectbox("삭제 대상 선택", df_ad['label'].tolist(), key="admin_select")
            if st.button("❌ 삭제", key="btn_admin_del"):
                df_ad = df_ad[df_ad['label'] != target_l]
                df_ad.drop(columns=['label']).to_csv(DB_FILE, index=False, encoding='utf-8-sig')
                st.rerun()

