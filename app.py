import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import os
from datetime import datetime, timedelta, timezone

# [필독] 구글 시트 설정
# 1. 구글 시트 공유 설정을 '링크가 있는 모든 사용자 - 편집자'로 변경하세요.
# 2. 아래 URL을 본인의 시트 주소로 교체하세요.
SHEET_URL = "https://docs.google.com/spreadsheets/d/1c6BlR4K2iRBU2gBY7iBsOHUIQmBZYXRqRbyLGct_HPI/edit?usp=sharing"

# 사진 저장 폴더 (서버 재시작 전까지 유지)
IMG_DIR = "id_cards"
if not os.path.exists(IMG_DIR):
    os.makedirs(IMG_DIR)

# --- [1. 핵심 함수 정의] ---

def get_kst_now():
    """서버 시간(UTC)을 한국 시간(KST)으로 변환합니다."""
    return datetime.now(timezone.utc) + timedelta(hours=9)

def get_latest_df():
    """구글 시트에서 최신 예약 데이터를 읽어옵니다."""
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        # ttl="0s"로 설정하여 캐시 없이 항상 실시간 데이터를 가져옵니다.
        return conn.read(spreadsheet=SHEET_URL, ttl="0s")
    except:
        # 시트가 비어있을 경우 기본 컬럼 생성
        return pd.DataFrame(columns=["학과", "이름", "학번", "인원", "날짜", "시작", "종료", "방번호", "출석", "사진파일명"])

def update_gsheet(df):
    """구글 시트에 전체 데이터를 업데이트합니다."""
    conn = st.connection("gsheets", type=GSheetsConnection)
    conn.update(spreadsheet=SHEET_URL, data=df)

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

# --- [2. 페이지 설정 및 디자인] ---
st.set_page_config(page_title="생명과학대학 스터디룸 예약", page_icon="🌿", layout="wide")

st.markdown("""
    <style>
    :root { --point-color: #A7D7C5; --point-dark: #3E7D6B; }
    .stButton>button { background-color: var(--point-color); color: white; border-radius: 10px; font-weight: bold; border: none; width: 100%; height: 3.2rem; font-size: 1.1rem; }
    .stButton>button:disabled { background-color: #E0E0E0 !important; color: #9E9E9E !important; cursor: not-allowed !important; }
    .schedule-card, .res-card { padding: 15px; border-radius: 12px; border-left: 6px solid var(--point-color); background-color: rgba(167, 215, 197, 0.1); margin-bottom: 12px; }
    .step-header { color: var(--point-dark); font-weight: bold; border-bottom: 2px solid var(--point-color); padding-bottom: 5px; margin-bottom: 15px; font-size: 1.2rem; }
    .success-receipt { border: 2px dashed var(--point-color); padding: 25px; border-radius: 15px; margin-top: 20px; background-color: white; color: black; }
    .receipt-title { color: var(--point-color); font-size: 1.5rem; font-weight: bold; text-align: center; margin-bottom: 20px; }
    .receipt-item { display: flex; justify-content: space-between; margin-bottom: 10px; border-bottom: 1px solid rgba(167, 215, 197, 0.3); padding-bottom: 5px; }
    </style>
    """, unsafe_allow_html=True)

now_kst = get_kst_now().replace(tzinfo=None)
current_time_str = now_kst.strftime("%H:%M")
time_options_all = [f"{h:02d}:{m:02d}" for h in range(0, 24) for m in (0, 30)]

# 데이터 로드 (매 실행마다 시트에서 새로 읽음)
df_all = get_latest_df()

# QR 체크인 로직 (URL 파라미터 확인)
q_params = st.query_params
if "checkin" in q_params:
    room_code = q_params["checkin"]
    target_room = "1번 스터디룸" if room_code == "room1" else "2번 스터디룸"
    now_date = str(now_kst.date())
    early_limit = (now_kst + timedelta(minutes=10)).strftime("%H:%M")
    
    mask = (df_all["방번호"] == target_room) & (df_all["날짜"] == now_date) & \
           (df_all["시작"] <= early_limit) & (df_all["종료"] > current_time_str) & (df_all["출석"] == "미입실")
    
    if any(mask):
        user_name = df_all.loc[mask, "이름"].values[0]
        df_all.loc[mask, "출석"] = "입실완료"
        update_gsheet(df_all)
        st.balloons()
        st.success(f"✅ 인증 성공: {user_name}님, 입실 확인되었습니다!")
        st.query_params.clear()
    else:
        st.warning("⚠️ 인증 실패: 예약 시간이 아니거나 이미 인증되었습니다.")

# --- [3. 사이드바 실시간 현황] ---
with st.sidebar:
    st.markdown(f"<h2 style='color:var(--point-color);'>📊 실시간 예약 현황</h2>", unsafe_allow_html=True)
    st.info(f"🕒 현재 시각: **{current_time_str}**")

    today_res = df_all[df_all["날짜"] == str(now_kst.date())]
    for r in ["1번 스터디룸", "2번 스터디룸"]:
        with st.expander(f"🚪 {r}", expanded=True):
            room_today = today_res[today_res["방번호"] == r].sort_values(by="시작")
            occ = room_today[((room_today["시작"] <= current_time_str) & (room_today["종료"] > current_time_str)) | 
                             ((room_today["출석"] == "입실완료") & (room_today["종료"] > current_time_str))]
            
            if not occ.empty:
                current_user = occ.iloc[0]
                status_color = "#3E7D6B" if current_user["출석"] == "입실완료" else "#E67E22"
                status_text = "현재 이용 중" if current_user["출석"] == "입실완료" else "인증 대기 중"
                
                st.markdown(f"""
                    <div style="margin-bottom: -15px;">
                        <h3 style="color:{status_color}; margin-bottom: 5px;">{status_text}</h3>
                        <p style="font-size: 1.1rem; font-weight: bold;">⏰ 종료 예정 시각: <span style="background-color: #f0f2f6; padding: 2px 5px; border-radius: 4px; color: black;">{current_user['종료']}</span></p>
                    </div>
                """, unsafe_allow_html=True)
                if current_user["출석"] == "미입실":
                    st.warning("⚠️ 15분 내 QR 인증 필요")
                st.divider()
            else:
                st.success("✨ 현재 비어 있음")

            next_res = room_today[room_today["시작"] > current_time_str]
            st.markdown("<p style='font-size: 0.9rem; font-weight: bold; margin-bottom: 5px;'>📅 다음 예약 안내</p>", unsafe_allow_html=True)
            if not next_res.empty:
                for _, row in next_res.iterrows():
                    st.caption(f"🕒 {row['시작']} ~ {row['종료']} (예약 완료)")
            else:
                st.caption("이후 예정된 예약이 없습니다.")

# --- [4. 메인 화면 구성] ---
st.title("생명과학대학 스터디룸 예약")
tabs = st.tabs(["📅 예약 신청", "🔍 내 예약 확인", "📋 전체 예약 일정", "➕ 시간 연장", "♻️ 반납 및 취소"])

with tabs[0]:
    if 'reserve_success' not in st.session_state:
        st.session_state.reserve_success = False
        st.session_state.last_res = {}

    if not st.session_state.reserve_success:
        st.markdown('<div class="step-header">1. 정보 입력</div>', unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        dept = c1.selectbox("🏢 학과", ["스마트팜과학과", "식품생명공학과", "유전생명공학과", "융합바이오·신소재공학과"], key="reg_dept")
        name = c2.text_input("👤 이름", key="reg_name")
        sid = c3.text_input("🆔 학번 (10자리 숫자)", key="reg_sid", max_chars=10, placeholder="예: 2024123456")
        count = c4.number_input("👥 인원 (최소 3명)", min_value=3, value=3, key="reg_count")
        
        # 학번 검증
        is_sid_valid = sid.isdigit() and len(sid) == 10
        if sid:
            if not sid.isdigit(): st.caption("❌ **숫자만** 입력 가능합니다.")
            elif len(sid) < 10: st.caption(f"⚠️ 현재 {len(sid)}자 / **10자리를 모두 입력해주세요.**")

        # 학생증 업로드
        st.markdown("##### 💳 학생증 사진 업로드 (본인 확인용)")
        id_file = st.file_uploader("파일을 선택하세요 (JPG, PNG)", type=['png', 'jpg', 'jpeg'])

        st.markdown('<div class="step-header">2. 장소 및 시간 선택</div>', unsafe_allow_html=True)
        sc1, sc2, tc1, tc2 = st.columns([2, 1, 1, 1])
        room = sc1.selectbox("🚪 장소", ["1번 스터디룸", "2번 스터디룸"], key="reg_room")
        date = sc2.date_input("📅 날짜", min_value=now_kst.date(), max_value=now_kst.date() + timedelta(days=13), key="reg_date")
        
        threshold_time = (now_kst - timedelta(minutes=15)).strftime("%H:%M")
        available_start = [t for t in time_options_all if t >= threshold_time] if str(date) == str(now_kst.date()) else time_options_all
        
        if not available_start: st.error("⚠️ 오늘은 더 이상 예약 가능한 시간이 없습니다.")
        else:
            st_t = tc1.selectbox("⏰ 시작", available_start, key="reg_start")
            en_t = tc2.selectbox("⏰ 종료", [t for t in time_options_all if t > st_t], key="reg_end")
            
            # 버튼 비활성화 조건: 이름, 학번(10자리), 학생증 업로드 완료 시 활성화
            submit_disabled = not (name.strip() and is_sid_valid and id_file is not None)
            
            if st.button("🚀 예약 신청", key="btn_reservation", disabled=submit_disabled):
                duration = datetime.strptime(en_t, "%H:%M") - datetime.strptime(st_t, "%H:%M")
                if duration > timedelta(hours=3): st.error("🚫 최대 이용 가능 시간은 3시간입니다.")
                elif is_already_booked(name, sid): st.error("🚫 이미 등록된 예약 내역이 존재합니다.")
                elif check_overlap(date, st_t, en_t, room): st.error("❌ 이미 예약된 시간입니다.")
                else:
                    # 사진 임시 저장
                    img_filename = f"{sid}_{datetime.now().strftime('%m%d%H%M%S')}.png"
                    with open(os.path.join(IMG_DIR, img_filename), "wb") as f:
                        f.write(id_file.getbuffer())
                    
                    # 데이터 저장 및 구글 시트 업데이트
                    new_data = [dept, name.strip(), sid.strip(), count, str(date), st_t, en_t, room, "미입실", img_filename]
                    df_new = pd.concat([df_all, pd.DataFrame([new_data], columns=df_all.columns)], ignore_index=True)
                    update_gsheet(df_new)
                    
                    st.session_state.reserve_success = True
                    st.session_state.last_res = {"name": name, "sid": sid, "room": room, "date": str(date), "start": st_t, "end": en_t}
                    st.rerun()
    else:
        res = st.session_state.last_res
        st.success("🎉 예약이 완료되었습니다!")
        st.markdown(f"""
            <div class="success-receipt">
                <div class="receipt-title">🌿 예약 확인서</div>
                <div class="receipt-item"><span>신청자</span><b>{res['name']} ({res['sid']})</b></div>
                <div class="receipt-item"><span>장소</span><b style="color: var(--point-color);">{res['room']}</b></div>
                <div class="receipt-item"><span>시간</span><b>{res['date']} / {res['start']} ~ {res['end']}</b></div>
            </div>
        """, unsafe_allow_html=True)
        if st.button("새로고침"):
            st.session_state.reserve_success = False
            st.rerun()

with tabs[1]:
    mc1, mc2 = st.columns(2)
    m_n, m_s = mc1.text_input("조회 이름", key="lookup_n"), mc2.text_input("조회 학번", key="lookup_s")
    if st.button("조회하기", key="btn_lookup"):
        res_list = df_all[(df_all["이름"] == m_n.strip()) & (df_all["학번"] == m_s.strip())]
        if not res_list.empty:
            for _, r in res_list.iterrows(): st.markdown(f'<div class="res-card">📍 {r["방번호"]} | {r["날짜"]} | ⏰ {r["시작"]}~{r["종료"]} | 상태: {r["출석"]}</div>', unsafe_allow_html=True)
        else: st.error("내역 없음")

with tabs[2]:
    if not df_all.empty:
        s_date = st.selectbox("날짜", sorted(df_all["날짜"].unique()), key="view_date")
        day_df = df_all[df_all["날짜"] == s_date].sort_values(by=["방번호", "시작"])
        for r_n in ["1번 스터디룸", "2번 스터디룸"]:
            st.markdown(f"#### 🚪 {r_n}")
            room_day = day_df[day_df["방번호"] == r_n]
            if room_day.empty: st.caption("예약 없음")
            else:
                for _, row in room_day.iterrows(): st.markdown(f'<div class="schedule-card"><b>{row["시작"]}~{row["종료"]}</b> | 예약완료</div>', unsafe_allow_html=True)
    else: st.info("현재 등록된 예약이 없습니다.")

with tabs[3]:
    st.markdown('<div class="step-header">➕ 이용 시간 연장</div>', unsafe_allow_html=True)
    en_n, en_id = st.text_input("이름 (연장)", key="ext_n"), st.text_input("학번 (연장)", key="ext_id")
    if st.button("연장 가능 여부 확인", key="btn_ext_check"):
        res_e = df_all[(df_all["이름"] == en_n.strip()) & (df_all["학번"] == en_id.strip()) & (df_all["날짜"] == str(now_kst.date()))]
        if not res_e.empty:
            target = res_e.iloc[-1]
            if target["출석"] != "입실완료": st.error("🚫 먼저 QR 인증을 통해 입실 확인을 해주세요.")
            else:
                end_dt = datetime.combine(now_kst.date(), datetime.strptime(target['종료'], "%H:%M").time())
                if (end_dt - timedelta(minutes=30)) <= now_kst < end_dt:
                    st.session_state['ext_target'] = target
                    st.success(f"✅ 연장 가능합니다. (현재 종료: {target['종료']})")
                else: st.warning("⚠️ 종료 30분 전부터 가능합니다.")
        else: st.error("🔍 오늘 예약 내역 없음")
            
    if 'ext_target' in st.session_state:
        target = st.session_state['ext_target']
        new_en = st.selectbox("새 종료 시각", [t for t in time_options_all if t > target['종료']][:4], key="ext_sel")
        if st.button("최종 연장 확정", key="btn_ext_confirm"):
            idx = df_all[(df_all["이름"] == en_n.strip()) & (df_all["학번"] == en_id.strip()) & (df_all["시작"] == target['시작'])].index
            df_all.loc[idx, "종료"] = new_en
            update_gsheet(df_all)
            st.success("✨ 연장 완료!"); del st.session_state['ext_target']; st.rerun()

with tabs[4]:
    can_n, can_id = st.text_input("이름 (취소)", key="can_n"), st.text_input("학번 (취소)", key="can_id")
    if st.button("조회", key="btn_can_lookup"):
        res_c = df_all[(df_all["이름"] == can_n.strip()) & (df_all["학번"] == can_id.strip())]
        if not res_c.empty: st.session_state['cancel_list'] = res_c
    if 'cancel_list' in st.session_state:
        opts = [f"{r['날짜']} | {r['방번호']} ({r['시작']}~{r['종료']})" for _, r in st.session_state['cancel_list'].iterrows()]
        target_idx = st.selectbox("선택", range(len(opts)), format_func=lambda x: opts[x])
        if st.button("최종 취소"):
            t = st.session_state['cancel_list'].iloc[target_idx]
            df_del = df_all.drop(df_all[(df_all["이름"] == t["이름"]) & (df_all["학번"] == t["학번"]) & (df_all["날짜"] == t["날짜"]) & (df_all["시작"] == t["시작"])].index)
            update_gsheet(df_del)
            del st.session_state['cancel_list']; st.rerun()

# --- [5. 관리자 메뉴] ---
st.markdown('<div style="height:100px;"></div>', unsafe_allow_html=True)
with st.expander("🛠️ 관리자 전용 메뉴"):
    pw = st.text_input("관리자 PW", type="password")
    if pw == "bio1234":
        st.write("### 📋 실시간 구글 시트 데이터")
        st.dataframe(df_all, use_container_width=True)
        
        if not df_all.empty:
            st.divider()
            st.write("### 🔍 학생증 사진 개별 확인")
            target_list = [f"{r['이름']} ({r['학번']}) - {r['날짜']}" for _, r in df_all.iterrows()]
            sel_idx = st.selectbox("학생 선택", range(len(target_list)), format_func=lambda x: target_list[x])
            
            target_row = df_all.iloc[sel_idx]
            img_path = os.path.join(IMG_DIR, str(target_row['사진파일명']))
            
            if os.path.exists(img_path):
                st.image(img_path, caption=f"{target_row['이름']} 학생증", width=400)
            else:
                st.warning("⚠️ 서버 재시작으로 사진 파일이 삭제되었습니다. 명단만 시트에서 확인 가능합니다.")
            
            if st.button("❌ 선택 예약 강제 삭제 (시트 반영)"):
                df_final = df_all.drop(df_all.index[sel_idx])
                update_gsheet(df_final)
                st.success("삭제되었습니다."); st.rerun()

