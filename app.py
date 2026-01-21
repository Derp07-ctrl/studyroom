import streamlit as st
import pandas as pd
import os
import urllib.parse
from datetime import datetime, timedelta, timezone

# 데이터 저장 파일명
DB_FILE = "reservations.csv"
# 새 로고 이미지 주소 반영
LOGO_URL = "https://ibb.co/xSy3YrhF"

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
    # 데이터 안정성을 위해 문자열 변환 및 공백 제거
    for col in ["이름", "학번", "날짜", "시작", "종료", "방번호"]:
        df[col] = df[col].astype(str).str.strip()
    return df

def is_already_booked(rep_name, rep_id):
    df = get_latest_df()
    if df.empty: return False
    duplicate = df[(df["이름"] == str(rep_name).strip()) & (df["학번"] == str(rep_id).strip())]
    return not duplicate.empty

def check_overlap(date, start_t, end_t, room):
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
    """예약 시작 15분 후 혹은 연장 후 15분 내 미인증 시 자동 삭제"""
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
    """URL 파라미터를 통한 QR 즉시 체크인"""
    q_params = st.query_params
    if "checkin" in q_params:
        room_code = q_params["checkin"]
        target_room = "1번 스터디룸" if room_code == "room1" else "2번 스터디룸"
        now_kst = get_kst_now().replace(tzinfo=None)
        now_date = str(now_kst.date())
        now_time = now_kst.strftime("%H:%M")
        early_limit = (now_kst + timedelta(minutes=10)).strftime("%H:%M")
        mask = (df["방번호"] == target_room) & (df["날짜"] == now_date) & \
               (df["시작"] <= early_limit) & (df["종료"] > now_time) & (df["출석"] == "미입실")
        if any(mask):
            user_name = df.loc[mask, "이름"].values[0]
            df.loc[mask, "출석"] = "입실완료"
            df.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
            st.success(f"✅ 인증 성공: {user_name}님, 입실 확인되었습니다!")
            st.query_params.clear()
        else:
            st.warning("⚠️ 인증 실패: 예약 시간이 아니거나 이미 인증되었습니다.")
    return df

# --- [2. 페이지 설정 및 디자인] ---
st.set_page_config(page_title="생명과학대학 스터디룸", page_icon=LOGO_URL, layout="wide")

st.markdown("""
    <style>
    :root { --point-color: #A7D7C5; --point-dark: #3E7D6B; }
    .stButton>button { background-color: var(--point-color); color: white; border-radius: 10px; font-weight: bold; border: none; width: 100%; }
    .schedule-card, .res-card { padding: 15px; border-radius: 12px; border-left: 6px solid var(--point-color); background-color: rgba(167, 215, 197, 0.1); margin-bottom: 12px; }
    .step-header { color: var(--point-dark); font-weight: bold; border-bottom: 2px solid var(--point-color); padding-bottom: 5px; margin-bottom: 15px; font-size: 1.2rem; }
    [data-testid="stSidebar"] img { border-radius: 15px; }
    </style>
    """, unsafe_allow_html=True)

now_kst = get_kst_now().replace(tzinfo=None)
current_time_str = now_kst.strftime("%H:%M")
time_options_all = [f"{h:02d}:{m:02d}" for h in range(0, 24) for m in (0, 30)]

df_all = get_latest_df()
df_all = auto_cleanup_noshow(df_all)
df_all = process_qr_checkin(df_all)

# --- [3. 사이드바 실시간 현황] ---
with st.sidebar:
    st.image(LOGO_URL, use_container_width=True)
    st.markdown(f"<h2 style='text-align: center; color:var(--point-color);'>📊 실시간 현황</h2>", unsafe_allow_html=True)
    st.info(f"🕒 **현재 시각** {current_time_str}")
    
    today_res = df_all[df_all["날짜"] == str(now_kst.date())]
    
    for r in ["1번 스터디룸", "2번 스터디룸"]:
        with st.expander(f"🚪 {r}", expanded=True):
            room_today = today_res[today_res["방번호"] == r].sort_values(by="시작")
            occ = room_today[((room_today["시작"] <= current_time_str) & (room_today["종료"] > current_time_str)) | 
                             ((room_today["출석"] == "입실완료") & (room_today["종료"] > current_time_str))]
            
            if not occ.empty:
                current_user = occ.iloc[0]
                status_text = "✅ 현재 사용 중" if current_user["출석"] == "입실완료" else "⚠️ 현재 예약 중"
                st.error(status_text)
                st.markdown(f"**{current_user['이름']}님 팀**")
                st.caption(f"⏰ {current_user['시작']} ~ {current_user['종료']}")
                if current_user["출석"] == "미입실":
                    st.warning("❗ 15분 내 QR 재인증 필요")
            else:
                st.success("✨ 현재 이용 가능")
            
            other_res = room_today[~room_today.index.isin(occ.index)]
            if not other_res.empty:
                st.markdown("<p style='font-size: 0.8rem; margin-top: 10px; font-weight: bold;'>📅 오늘 전체 일정</p>", unsafe_allow_html=True)
                for _, or_row in other_res.iterrows():
                    st.caption(f"🕒 {or_row['시작']} ~ {or_row['종료']} ({or_row['이름']}님)")

# --- [4. 메인 화면 구성] ---
col_logo, col_title = st.columns([1, 10])
with col_logo:
    st.image(LOGO_URL, width=70)
with col_title:
    st.title("생명과학대학 스터디룸 예약")

tabs = st.tabs(["📅 예약 신청", "🔍 내 예약 확인", "📋 전체 일정", "➕ 시간 연장", "♻️ 반납 및 취소"])

with tabs[0]:
    st.markdown('<div class="step-header">1. 정보 입력</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    dept = c1.selectbox("🏢 학과", ["스마트팜과학과", "식품생명공학과", "유전생명공학과", "융합바이오·신소재공학과"], key="reg_dept")
    name = c2.text_input("👤 이름", key="reg_name")
    sid = c3.text_input("🆔 학번", key="reg_sid")
    count = c4.number_input("👥 인원 (최소 3명)", min_value=3, value=3, key="reg_count")
    
    st.markdown('<div class="step-header">2. 장소 및 시간 선택</div>', unsafe_allow_html=True)
    sc1, sc2, tc1, tc2 = st.columns([2, 1, 1, 1])
    room = sc1.selectbox("🚪 장소", ["1번 스터디룸", "2번 스터디룸"], key="reg_room")
    date = sc2.date_input("📅 날짜", min_value=now_kst.date(), key="reg_date")
    
    available_start = [t for t in time_options_all if t > current_time_str] if str(date) == str(now_kst.date()) else time_options_all
    if not available_start: st.error("오늘 예약 종료")
    else:
        st_t = tc1.selectbox("⏰ 시작", available_start, key="reg_start")
        en_t = tc2.selectbox("⏰ 종료", [t for t in time_options_all if t > st_t], key="reg_end")
        if st.button("🚀 예약 신청", key="btn_reservation"):
            if not (name.strip() and sid.strip()): st.error("정보 미입력")
            elif is_already_booked(name, sid): st.error("이미 예약이 존재합니다.")
            elif (datetime.strptime(en_t, "%H:%M") - datetime.strptime(st_t, "%H:%M")) > timedelta(hours=3): st.error("최대 3시간 가능")
            elif check_overlap(date, st_t, en_t, room): st.error("중복 예약")
            else:
                pd.DataFrame([[dept, name, sid, count, str(date), st_t, en_t, room, "미입실"]], columns=df_all.columns).to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False, encoding='utf-8-sig')
                st.success("예약 완료!"); st.rerun()

with tabs[1]:
    mc1, mc2 = st.columns(2)
    m_n, m_s = mc1.text_input("조회 이름", key="lookup_n"), mc2.text_input("조회 학번", key="lookup_s")
    if st.button("조회하기", key="btn_lookup"):
        res = get_latest_df()[(get_latest_df()["이름"] == m_n.strip()) & (get_latest_df()["학번"] == m_s.strip())]
        if not res.empty:
            for _, r in res.iterrows(): st.markdown(f'<div class="res-card">📍 {r["방번호"]} | {r["날짜"]} | ⏰ {r["시작"]}~{r["종료"]} | {r["출석"]}</div>', unsafe_allow_html=True)
        else: st.error("내역 없음")

with tabs[2]:
    df_v = get_latest_df()
    if not df_v.empty:
        s_date = st.selectbox("날짜", sorted(df_v["날짜"].unique()), key="view_date")
        day_df = df_v[df_v["날짜"] == s_date].sort_values(by=["방번호", "시작"])
        for r_n in ["1번 스터디룸", "2번 스터디룸"]:
            st.markdown(f"#### 🚪 {r_n}")
            room_day = day_df[day_df["방번호"] == r_n]
            if room_day.empty: st.caption("예약 없음")
            else:
                for _, row in room_day.iterrows(): st.markdown(f'<div class="schedule-card"><b>{row["시작"]}~{row["종료"]}</b> | {row["이름"]}</div>', unsafe_allow_html=True)
    else: st.info("데이터 없음")

with tabs[3]:
    st.markdown('<div class="step-header">➕ 이용 시간 연장</div>', unsafe_allow_html=True)
    en_n, en_id = st.text_input("이름", key="ext_n"), st.text_input("학번", key="ext_id")
    if st.button("연장 가능 여부 확인", key="btn_ext_check"):
        df_e = get_latest_df()
        res_e = df_e[(df_e["이름"] == en_n.strip()) & (df_e["학번"] == en_id.strip()) & (df_e["날짜"] == str(now_kst.date()))]
        if not res_e.empty:
            target = res_e.iloc[-1]
            end_dt = datetime.combine(now_kst.date(), datetime.strptime(target['종료'], "%H:%M").time())
            if (end_dt - timedelta(minutes=30)) <= now_kst < end_dt:
                st.session_state['ext_target'] = target
                st.success("연장 가능 시간입니다.")
            else: st.warning("연장은 종료 30분 전부터 가능합니다.")
            
    if 'ext_target' in st.session_state:
        target = st.session_state['ext_target']
        new_en = st.selectbox("새 종료 시각", [t for t in time_options_all if t > target['종료']][:4], key="ext_sel")
        st.info("⚠️ 연장 시 15분 이내에 QR 코드를 다시 스캔해야 합니다.")
        if st.button("연장 확정", key="btn_ext_confirm"):
            df_up = get_latest_df()
            idx = df_up[(df_up["이름"] == en_n.strip()) & (df_up["학번"] == en_id.strip()) & (df_up["시작"] == target['시작'])].index
            df_up.loc[idx, "종료"] = new_en
            df_up.loc[idx, "출석"] = "미입실"
            df_up.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
            st.success("연장 완료! 15분 내로 QR 재인증을 해주세요."); del st.session_state['ext_target']; st.rerun()

with tabs[4]:
    can_n, can_id = st.text_input("이름", key="can_n"), st.text_input("학번", key="can_id")
    if st.button("내 예약 조회", key="btn_can_lookup"):
        res_c = get_latest_df()[(get_latest_df()["이름"] == can_n.strip()) & (get_latest_df()["학번"] == can_id.strip())]
        if not res_c.empty: st.session_state['cancel_list'] = res_c
    if 'cancel_list' in st.session_state:
        opts = [f"{r['날짜']} | {r['방번호']} ({r['시작']}~{r['종료']})" for _, r in st.session_state['cancel_list'].iterrows()]
        target_idx = st.selectbox("대상 선택", range(len(opts)), format_func=lambda x: opts[x])
        if st.button("최종 반납 및 취소 확정", type="primary"):
            df_del = get_latest_df(); t = st.session_state['cancel_list'].iloc[target_idx]
            df_del.drop(df_del[(df_del["이름"] == t["이름"]) & (df_del["학번"] == t["학번"]) & (df_del["날짜"] == t["날짜"]) & (df_del["시작"] == t["시작"])].index).to_csv(DB_FILE, index=False, encoding='utf-8-sig')
            del st.session_state['cancel_list']; st.rerun()

with st.expander("🛠️ 관리자"):
    pw = st.text_input("Password", type="password", key="admin_pw")
    if pw == "bio1234":
        df_ad = get_latest_df()
        st.dataframe(df_ad, use_container_width=True)
        if not df_ad.empty:
            labels = [f"{r['이름']} | {r['방번호']}" for _, r in df_ad.iterrows()]
            sel = st.selectbox("대상 선택", range(len(labels)), format_func=lambda x: labels[x])
            if st.button("강제 삭제"):
                t = df_ad.iloc[sel]
                df_ad.drop(df_ad[(df_ad["이름"] == t["이름"]) & (df_ad["학번"] == t["학번"]) & (df_ad["날짜"] == t["날짜"]) & (df_ad["시작"] == t["시작"])].index).to_csv(DB_FILE, index=False, encoding='utf-8-sig')
                st.rerun()
