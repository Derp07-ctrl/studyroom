import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import os
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

# --- [2. 페이지 설정 및 디자인] ---
st.set_page_config(page_title="생명과학대학 스터디룸 예약", page_icon="🌿", layout="wide")

st.markdown("""
    <style>
    :root { --point-color: #A7D7C5; --point-dark: #3E7D6B; }
    .stButton>button { background-color: var(--point-color); color: white; border-radius: 10px; font-weight: bold; border: none; width: 100%; }
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

df_all = get_latest_df()
df_all = auto_cleanup_noshow(df_all)
df_all = process_qr_checkin(df_all)

# --- [3. 사이드바 실시간 현황] ---
with st.sidebar:
    st.markdown(f"<h2 style='color:var(--point-color);'>📊 실시간 예약 현황</h2>", unsafe_allow_html=True)

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
                st.success("현재 비어 있음")

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
        
        # [수정] 학번 입력 제한: 숫자만 10자리
        sid = c3.text_input("🆔 학번", key="reg_sid", max_chars=10, placeholder="예: 2024123456")
        count = c4.number_input("👥 인원 (최소 3명)", min_value=3, value=3, key="reg_count")
        
        # 유효성 검사 (숫자인지 && 10자리인지)
        is_sid_valid = sid.isdigit() and len(sid) == 10
        if sid:
            if not sid.isdigit(): st.caption("❌ **숫자만** 입력 가능합니다.")
            elif len(sid) < 10: st.caption(f"⚠️ 현재 {len(sid)}자 / **10자리를 모두 입력해주세요.**")

        st.markdown('<div class="step-header">2. 장소 및 시간 선택</div>', unsafe_allow_html=True)
        sc1, sc2, tc1, tc2 = st.columns([2, 1, 1, 1])
        room = sc1.selectbox("🚪 장소", ["1번 스터디룸", "2번 스터디룸"], key="reg_room")
        date = sc2.date_input("📅 날짜", 
                              min_value=now_kst.date(), 
                              max_value=now_kst.date() + timedelta(days=13), 
                              key="reg_date")
        
        threshold_time = (now_kst - timedelta(minutes=15)).strftime("%H:%M")
        available_start = [t for t in time_options_all if t >= threshold_time] if str(date) == str(now_kst.date()) else time_options_all
        
        if not available_start: st.error("⚠️ 오늘은 더 이상 예약 가능한 시간이 없습니다.")
        else:
            st_t = tc1.selectbox("⏰ 시작", available_start, key="reg_start")
            en_t = tc2.selectbox("⏰ 종료", [t for t in time_options_all if t > st_t], key="reg_end")
            
            # 버튼 활성화 조건: 이름 입력 AND 학번 10자리 숫자 성공 시 활성화
            submit_disabled = not (name.strip() and is_sid_valid)
            
            if st.button("🚀 예약 신청", key="btn_reservation", disabled=submit_disabled):
                duration = datetime.strptime(en_t, "%H:%M") - datetime.strptime(st_t, "%H:%M")
                if duration > timedelta(hours=3): st.error("🚫 최대 이용 가능 시간은 3시간입니다.")
                elif is_already_booked(name, sid): st.error("🚫 이미 등록된 예약 내역이 존재합니다.")
                elif check_overlap(date, st_t, en_t, room): st.error("❌ 이미 예약된 시간입니다.")
                else:
                    new_data = [dept, name.strip(), sid.strip(), count, str(date), st_t, en_t, room, "미입실"]
                    pd.DataFrame([new_data], columns=df_all.columns).to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False, encoding='utf-8-sig')
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
        
# [나머지 탭 동일]
with tabs[1]:
    mc1, mc2 = st.columns(2)
    m_n, m_s = mc1.text_input("조회 이름", key="lookup_n"), mc2.text_input("조회 학번", key="lookup_s")
    if st.button("조회하기", key="btn_lookup"):
        res_list = get_latest_df()[(get_latest_df()["이름"] == m_n.strip()) & (get_latest_df()["학번"] == m_s.strip())]
        if not res_list.empty:
            for _, r in res_list.iterrows(): st.markdown(f'<div class="res-card">📍 {r["방번호"]} | {r["날짜"]} | ⏰ {r["시작"]}~{r["종료"]} | 상태: {r["출석"]}</div>', unsafe_allow_html=True)
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
                for _, row in room_day.iterrows(): st.markdown(f'<div class="schedule-card"><b>{row["시작"]}~{row["종료"]}</b> | 예약완료</div>', unsafe_allow_html=True)
    else: st.info("현재 예약이 없습니다.")

with tabs[3]:
    st.markdown('<div class="step-header">➕ 이용 시간 연장</div>', unsafe_allow_html=True)
    en_n, en_id = st.text_input("이름 (연장)", key="ext_n"), st.text_input("학번 (연장)", key="ext_id")
    
    if st.button("연장 가능 여부 확인", key="btn_ext_check"):
        df_e = get_latest_df()
        res_e = df_e[(df_e["이름"] == en_n.strip()) & (df_e["학번"] == en_id.strip()) & (df_e["날짜"] == str(now_kst.date()))]
        
        if not res_e.empty:
            target = res_e.iloc[-1]
            if target["출석"] != "입실완료":
                st.error("🚫 먼저 QR 인증을 통해 입실 확인을 해주세요. 미인증 상태에서는 연장이 불가능합니다.")
            else:
                end_dt = datetime.combine(now_kst.date(), datetime.strptime(target['종료'], "%H:%M").time())
                
                # 종료 30분 전부터 종료 시각까지만 연장 신청 가능
                if (end_dt - timedelta(minutes=30)) <= now_kst < end_dt:
                    st.session_state['ext_target'] = target
                    st.success(f"✅ 본인 확인 완료. 현재 종료 시각은 {target['종료']}입니다.")
                else:
                    st.warning("⚠️ 연장은 이용 종료 30분 전부터 종료 시각까지만 가능합니다.")
        else:
            st.error("🔍 오늘 날짜로 예약된 내역을 찾을 수 없습니다.")

    # 연장 세부 설정
    if 'ext_target' in st.session_state:
        target = st.session_state['ext_target']
        df_full = get_latest_df()
        
        # [핵심 로직] 현재 예약의 종료 시간 이후로 가장 빨리 시작되는 다음 예약 찾기
        next_reservations = df_full[
            (df_full["방번호"] == target["방번호"]) & 
            (df_full["날짜"] == target["날짜"]) & 
            (df_all["시작"] >= target["종료"])
        ].sort_values(by="시작")
        
        # 다음 예약이 있으면 그 시작 시간을 한계점으로 잡고, 없으면 밤 24:00를 한계점으로 설정
        limit_time_str = next_reservations.iloc[0]["시작"] if not next_reservations.empty else "23:59"
        limit_dt = datetime.combine(now_kst.date(), datetime.strptime(limit_time_str if limit_time_str != "23:59" else "23:59", "%H:%M").time())
        
        # 현재 종료 시간부터 최대 2시간(4슬롯)까지 옵션 생성
        current_end_dt = datetime.strptime(target['종료'], "%H:%M")
        possible_options = []
        for i in range(1, 5): # 30분, 60분, 90분, 120분 체크
            check_dt = current_end_dt + timedelta(minutes=30 * i)
            check_str = check_dt.strftime("%H:%M")
            
            # 한계 시간(다음 예약 시작 시간)보다 작거나 같을 때만 옵션에 추가
            if check_dt.time() <= limit_dt.time():
                possible_options.append(check_str)
            else:
                break
        
        if not possible_options:
            st.error(f"❌ 다음 예약({limit_time_str})이 바로 뒤에 있어 연장이 불가능합니다.")
        else:
            st.info(f"✨ 뒤에 예약이 없어 최대 {possible_options[-1]}까지 연장 가능합니다.")
            new_en = st.selectbox("연장할 종료 시각 선택", possible_options, key="ext_sel_box")
            
            if st.button("최종 연장 확정", key="btn_ext_confirm"):
                df_up = get_latest_df()
                idx = df_up[(df_up["이름"] == en_n.strip()) & (df_up["학번"] == en_id.strip()) & (df_up["시작"] == target['시작'])].index
                
                df_up.loc[idx, "종료"] = new_en
                df_up.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
                
                st.success(f"✨ 연장 완료! {new_en}까지 이용 가능합니다.")
                del st.session_state['ext_target']
                st.rerun()
                
with tabs[4]:
    can_n, can_id = st.text_input("이름 (취소)", key="can_n"), st.text_input("학번 (취소)", key="can_id")
    if st.button("조회", key="btn_can_lookup"):
        res_c = get_latest_df()[(get_latest_df()["이름"] == can_n.strip()) & (get_latest_df()["학번"] == can_id.strip())]
        if not res_c.empty: st.session_state['cancel_list'] = res_c
    if 'cancel_list' in st.session_state:
        opts = [f"{r['날짜']} | {r['방번호']} ({r['시작']}~{r['종료']})" for _, r in st.session_state['cancel_list'].iterrows()]
        target_idx = st.selectbox("선택", range(len(opts)), format_func=lambda x: opts[x])
        if st.button("최종 취소"):
            df_del = get_latest_df(); t = st.session_state['cancel_list'].iloc[target_idx]
            df_del.drop(df_del[(df_del["이름"] == t["이름"]) & (df_del["학번"] == t["학번"]) & (df_del["날짜"] == t["날짜"]) & (df_del["시작"] == t["시작"])].index).to_csv(DB_FILE, index=False, encoding='utf-8-sig')
            del st.session_state['cancel_list']; st.rerun()

# --- [5. 관리자 메뉴] ---
st.markdown('<div style="height:100px;"></div>', unsafe_allow_html=True)
with st.expander("🛠️ 관리자 전용 메뉴"):
    pw = st.text_input("관리자 비밀번호", type="password", key="admin_pw")
    if pw == "bio1234":
        df_ad = get_latest_df()
        if not df_ad.empty:
            st.dataframe(df_ad, use_container_width=True)
            labels = [f"{r['이름']} | {r['날짜']} | {r['시작']} ({r['방번호']})" for _, r in df_ad.iterrows()]
            sel = st.selectbox("강제 삭제할 대상을 선택하세요", range(len(labels)), format_func=lambda x: labels[x])
            if st.button("퇴실/삭제"):
                t = df_ad.iloc[sel]
                df_ad = df_ad.drop(df_ad[(df_ad["이름"] == t["이름"]) & (df_ad["학번"] == t["학번"]) & (df_ad["날짜"] == t["날짜"]) & (df_ad["시작"] == t["시작"])].index)
                df_ad.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
                st.success("관리자 권한으로 강제 삭제되었습니다.")
                st.rerun()
        else:
            st.info("현재 관리할 예약 내역이 없습니다.")


















