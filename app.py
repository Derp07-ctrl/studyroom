import streamlit as st
import pandas as pd
import os
from datetime import datetime, timedelta, timezone

# 데이터 저장 파일명
DB_FILE = "reservations.csv"
HISTORY_FILE = "history.csv"

# --- [1. 핵심 함수 정의] ---

def get_kst_now():
    """서버 시간(UTC)을 한국 시간(KST)으로 변환합니다."""
    return datetime.now(timezone.utc) + timedelta(hours=9)

def get_latest_df():
    """실시간 예약 데이터를 읽어옵니다."""
    if not os.path.isfile(DB_FILE):
        return pd.DataFrame(columns=["학과", "이름", "학번", "인원", "날짜", "시작", "종료", "방번호", "출석", "팀원학번"])
    df = pd.read_csv(DB_FILE)
    if "출석" not in df.columns: df["출석"] = "미입실"
    if "팀원학번" not in df.columns: df["팀원학번"] = ""
    for col in ["이름", "학번", "날짜", "시작", "종료", "방번호", "팀원학번"]:
        df[col] = df[col].astype(str).str.strip()
    return df

def process_qr_checkin(df):
    """QR 코드를 통한 입실 처리를 수행합니다."""
    q_params = st.query_params
    if "checkin" in q_params:
        room_code = q_params["checkin"]
        target_room = "1번 스터디룸" if room_code == "room1" else "2번 스터디룸"
        
        now_kst = get_kst_now().replace(tzinfo=None)
        now_date = str(now_kst.date())
        now_time = now_kst.strftime("%H:%M")
        
        # 예약 시작 10분 전부터 종료 시각 전까지만 인증 가능
        early_limit = (now_kst + timedelta(minutes=10)).strftime("%H:%M")
        
        mask = (df["방번호"] == target_room) & \
               (df["날짜"] == now_date) & \
               (df["시작"] <= early_limit) & \
               (df["종료"] > now_time) & \
               (df["출석"] == "미입실")
        
        if any(mask):
            idx = df[mask].index[0]
            user_name = df.loc[idx, "이름"]
            df.loc[idx, "출석"] = "입실완료"
            df.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
            st.balloons()
            st.success(f"✅ 인증 성공: {user_name}님, {target_room} 입실 확인되었습니다!")
            st.query_params.clear()
        else:
            st.warning(f"⚠️ {target_room} 인증 실패: 현재 예약 시간이 아니거나 이미 인증되었습니다.")
    return df

def check_team_duplication(member_ids, target_date):
    df = get_latest_df()
    if df.empty: return False, ""
    day_df = df[df["날짜"] == str(target_date)]
    for m_id in member_ids:
        if not m_id: continue
        is_booked = day_df[(day_df["학번"] == m_id) | (day_df["팀원학번"].str.contains(m_id, na=False))]
        if not is_booked.empty: return True, m_id
    return False, ""

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
    .stButton>button { background-color: var(--point-color); color: white; border-radius: 10px; font-weight: bold; border: none; width: 100%; height: 3.2rem; }
    .step-header { color: var(--point-dark); font-weight: bold; border-bottom: 2px solid var(--point-color); padding-bottom: 5px; margin-bottom: 15px; font-size: 1.1rem; }
    .schedule-card, .res-card { padding: 15px; border-radius: 12px; border-left: 6px solid var(--point-color); background-color: rgba(167, 215, 197, 0.1); margin-bottom: 12px; }
    </style>
    """, unsafe_allow_html=True)

now_kst = get_kst_now().replace(tzinfo=None)
current_time_str = now_kst.strftime("%H:%M")
time_options_all = [f"{h:02d}:{m:02d}" for h in range(0, 24) for m in (0, 30)]
depts = ["스마트팜과학과", "식품생명공학과", "유전생명공학과", "융합바이오·신소재공학과"]

# 데이터 로드 및 QR 입실 처리 수행
df_all = get_latest_df()
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
                st.markdown(f'<h3 style="color:{status_color};">{"현재 이용 중" if current_user["출석"] == "입실완료" else "인증 대기 중"}</h3>', unsafe_allow_html=True)
                st.markdown(f"**⏰ 종료 예정: {current_user['종료']}**")
            else:
                st.success("현재 비어 있음")
            
            next_res = room_today[room_today["시작"] > current_time_str]
            if not next_res.empty:
                st.markdown("<p style='font-size: 0.85rem; color: gray;'>다음 예약:</p>", unsafe_allow_html=True)
                for _, nr in next_res.iterrows():
                    st.caption(f"🕒 {nr['시작']} ~ {nr['종료']}")

# --- [4. 메인 화면 구성] ---
st.title("생명과학대학 스터디룸 예약")
tabs = st.tabs(["📅 예약 신청", "🔍 내 예약 확인", "📋 전체 예약 일정", "➕ 시간 연장", "♻️ 반납 및 취소"])

with tabs[0]: # 예약 신청
    if 'reserve_success' not in st.session_state: st.session_state.reserve_success = False
    
    if not st.session_state.reserve_success:
        st.markdown('<div class="step-header">1. 이용 인원 및 정보 입력</div>', unsafe_allow_html=True)
        ic1, _ = st.columns([1, 2])
        total_count = ic1.selectbox("이용 인원", [3, 4, 5, 6], key="reg_count")
        
        st.write("**👤 대표자**")
        rc1, rc2, rc3 = st.columns([1.5, 1.2, 1])
        rep_dept = rc1.selectbox("학과", depts, key="rep_dept", label_visibility="collapsed")
        rep_name = rc2.text_input("이름", key="rep_name", placeholder="성함", label_visibility="collapsed")
        rep_id = rc3.text_input("학번", key="rep_id", max_chars=10, placeholder="10자리", label_visibility="collapsed")

        st.write(f"**👥 구성원 ({total_count-1}명)**")
        m_names, m_ids = [], []
        for i in range(total_count - 1):
            mc1, mc2, mc3 = st.columns([1.5, 1.2, 1])
            mc1.selectbox(f"학과{i}", depts, key=f"m_dept_{i}", label_visibility="collapsed")
            m_n = mc2.text_input(f"이름{i}", key=f"m_n_{i}", placeholder="성함", label_visibility="collapsed")
            m_i = mc3.text_input(f"학번{i}", key=f"m_id_{i}", max_chars=10, placeholder="10자리", label_visibility="collapsed")
            m_names.append(m_n.strip()); m_ids.append(m_i.strip())

        st.markdown('<div class="step-header">2. 예약 날짜/장소/시간 선택</div>', unsafe_allow_html=True)
        sc1, sc2, tc1, tc2 = st.columns([1.2, 1.2, 1, 1])
        room = sc1.selectbox("🚪 장소", ["1번 스터디룸", "2번 스터디룸"], key="reg_room")
        sel_date = sc2.selectbox("📅 날짜", [now_kst.date(), (now_kst + timedelta(days=1)).date()], key="reg_date")
        st_t = tc1.selectbox("⏰ 시작", time_options_all, key="reg_start")
        en_t = tc2.selectbox("⏰ 종료", [t for t in time_options_all if t > st_t], key="reg_end")

        if st.button("🚀 예약 신청하기"):
            all_ids = [rep_id.strip()] + m_ids
            id_to_name = {rep_id.strip(): rep_name.strip()}
            for mid, mname in zip(m_ids, m_names): id_to_name[mid] = mname

            is_ready = rep_name and len(rep_id)==10 and all(m_names) and all(len(idx)==10 for idx in all_ids)
            if not is_ready:
                st.error("⚠️ 모든 정보를 정확히 입력해주세요.")
            else:
                dup, culprit_id = check_team_duplication(all_ids, sel_date)
                if dup:
                    c_name = id_to_name.get(culprit_id, culprit_id)
                    st.error(f"❌ '{c_name}'님은 해당 날짜에 이미 예약이 있습니다."); st.stop()
                if check_overlap(sel_date, st_t, en_t, room):
                    st.error("❌ 이미 예약된 시간입니다."); st.stop()
                
                new_row = [rep_dept, rep_name.strip(), rep_id.strip(), total_count, str(sel_date), st_t, en_t, room, "미입실", ",".join(m_ids)]
                
                # 1. 실시간 데이터 저장
                pd.DataFrame([new_row], columns=get_latest_df().columns).to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False, encoding='utf-8-sig')
                
                # 2. 누적 히스토리 저장
                history_df = pd.DataFrame([new_row], columns=get_latest_df().columns)
                history_df["신청일시"] = get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
                history_df.to_csv(HISTORY_FILE, mode='a', header=not os.path.exists(HISTORY_FILE), index=False, encoding='utf-8-sig')
                
                st.session_state.reserve_success = True; st.rerun()
    else:
        st.success("🎉 예약 신청이 완료되었습니다!"); if st.button("처음으로"): st.session_state.reserve_success = False; st.rerun()

with tabs[1]: # 내 예약 확인
    st.markdown('<div class="step-header">🔍 내 예약 확인 (대표자/구성원 공통)</div>', unsafe_allow_html=True)
    mc1, mc2 = st.columns(2)
    m_n = mc1.text_input("이름 입력", key="lookup_n")
    m_s = mc2.text_input("학번 입력 (10자리)", key="lookup_s")
    if st.button("내역 조회하기"):
        df_curr = get_latest_df()
        res_list = df_curr[((df_curr["이름"] == m_n.strip()) & (df_curr["학번"] == m_s.strip())) | (df_curr["팀원학번"].str.contains(m_s.strip(), na=False))]
        if not res_list.empty:
            for _, r in res_list.iterrows(): st.markdown(f'<div class="res-card">📍 {r["방번호"]} | {r["날짜"]} | ⏰ {r["시작"]}~{r["종료"]} | 상태: {r["출석"]}</div>', unsafe_allow_html=True)
        else: st.error("조회된 예약 내역이 없습니다.")

with tabs[2]: # 전체 일정
    st.markdown('<div class="step-header">📋 스터디룸별 전체 예약 일정</div>', unsafe_allow_html=True)
    df_v = get_latest_df()
    if not df_v.empty:
        s_date = st.selectbox("날짜 선택", sorted(df_v["날짜"].unique()), key="view_date")
        day_df = df_v[df_v["날짜"] == s_date].sort_values(by=["방번호", "시작"])
        for r_n in ["1번 스터디룸", "2번 스터디룸"]:
            st.markdown(f"#### 🚪 {r_n}")
            room_day = day_df[day_df["방번호"] == r_n]
            if room_day.empty: st.caption("해당 날짜에 예약이 없습니다.")
            else:
                for _, row in room_day.iterrows(): st.markdown(f'<div class="schedule-card"><b>{row["시작"]}~{row["종료"]}</b> | 예약 완료</div>', unsafe_allow_html=True)
    else: st.info("현재 등록된 예약이 없습니다.")

with tabs[3]: # 시간 연장
    st.markdown('<div class="step-header">➕ 이용 시간 연장 (대표자/구성원 공통)</div>', unsafe_allow_html=True)
    ec1, ec2 = st.columns(2)
    ext_n = ec1.text_input("이름 (연장)", key="ext_n_input")
    ext_id = ec2.text_input("학번 (연장)", key="ext_id_input")
    if st.button("연장 가능 여부 확인"):
        df_e = get_latest_df()
        res_e = df_e[((df_e["학번"] == ext_id.strip()) | (df_e["팀원학번"].str.contains(ext_id.strip(), na=False))) & (df_e["날짜"] == str(now_kst.date()))]
        if not res_e.empty:
            target = res_e.iloc[-1]
            if target["출석"] != "입실완료": st.error("🚫 QR 입실 인증 후에만 연장이 가능합니다.")
            else:
                st.session_state['ext_target'] = target; st.success(f"✅ 확인됨: {target['종료']} 종료 예정")
        else: st.error("🔍 오늘 이용 중인 예약 내역을 찾을 수 없습니다.")
    
    if 'ext_target' in st.session_state:
        target = st.session_state['ext_target']
        df_f = get_latest_df()
        next_res = df_f[(df_f["방번호"] == target["방번호"]) & (df_f["날짜"] == target["날짜"]) & (df_f["시작"] >= target["종료"])].sort_values(by="시작")
        limit_t = next_res.iloc[0]["시작"] if not next_res.empty else "23:59"
        curr_en_dt = datetime.strptime(target['종료'], "%H:%M")
        opts = [(curr_en_dt + timedelta(minutes=30*i)).strftime("%H:%M") for i in range(1, 5) if (curr_en_dt + timedelta(minutes=30*i)).time() <= datetime.strptime(limit_t, "%H:%M").time()]
        if not opts: st.warning("다음 예약 일정으로 인해 연장이 불가합니다.")
        else:
            new_en = st.selectbox("연장할 종료 시각", opts)
            if st.button("최종 연장 확정"):
                df_up = get_latest_df()
                idx = df_up[(df_up["날짜"] == target["날짜"]) & (df_up["방번호"] == target["방번호"]) & (df_up["시작"] == target["시작"])].index
                df_up.loc[idx, "종료"] = new_en
                df_up.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
                st.success(f"연장 완료! (~{new_en})"); del st.session_state['ext_target']; st.rerun()

with tabs[4]: # 취소/반납
    st.markdown('<div class="step-header">♻️ 예약 반납 및 취소 (대표자/구성원 공통)</div>', unsafe_allow_html=True)
    cc1, cc2 = st.columns(2)
    can_n = cc1.text_input("이름 (취소)", key="can_n_input")
    can_id = cc2.text_input("학번 (취소)", key="can_id_input")
    if st.button("내 예약 찾기 (취소용)"):
        df_c = get_latest_df()
        res_c = df_c[(df_c["학번"] == can_id.strip()) | (df_c["팀원학번"].str.contains(can_id.strip(), na=False))]
        if not res_c.empty: st.session_state['cancel_list'] = res_c
        else: st.error("🔍 예약 내역이 없습니다.")
    if 'cancel_list' in st.session_state:
        opts = [f"{r['날짜']} | {r['방번호']} ({r['시작']}~{r['종료']})" for _, r in st.session_state['cancel_list'].iterrows()]
        sel_idx = st.selectbox("취소할 내역 선택", range(len(opts)), format_func=lambda x: opts[x])
        if st.button("최종 취소/반납 처리"):
            t = st.session_state['cancel_list'].iloc[sel_idx]
            df_curr_f = get_latest_df()
            df_final = df_curr_f.drop(df_curr_f[(df_curr_f["날짜"] == t["날짜"]) & (df_curr_f["방번호"] == t["방번호"]) & (df_curr_f["시작"] == t["시작"])].index)
            df_final.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
            st.success("정상적으로 처리되었습니다."); del st.session_state['cancel_list']; st.rerun()

# --- [5. 관리자 메뉴] ---
st.markdown('<div style="height:100px;"></div>', unsafe_allow_html=True)
with st.expander("🛠️ 관리자 전용 메뉴"):
    pw = st.text_input("관리자 비밀번호", type="password", key="admin_pw")
    if pw == "bio1234":
        admin_tab1, admin_tab2 = st.tabs(["📝 실시간 예약 관리", "📜 누적 전체 기록"])
        with admin_tab1:
            st.markdown("#### 📍 현재 활성 예약 목록")
            df_ad = get_latest_df()
            if not df_ad.empty:
                st.dataframe(df_ad, use_container_width=True)
                labels = [f"{r['이름']} | {r['날짜']} | {r['시작']} ({r['방번호']})" for _, r in df_ad.iterrows()]
                sel_ad = st.selectbox("삭제 대상을 선택하세요", range(len(labels)), format_func=lambda x: labels[x])
                if st.button("관리자 강제 삭제"):
                    t_ad = df_ad.iloc[sel_ad]
                    df_final_ad = get_latest_df().drop(df_ad[(df_ad["날짜"] == t_ad["날짜"]) & (df_ad["방번호"] == t_ad["방번호"]) & (df_ad["시작"] == t_ad["시작"])].index)
                    df_final_ad.to_csv(DB_FILE, index=False, encoding='utf-8-sig'); st.rerun()
            else: st.info("활성 예약 내역이 없습니다.")
        with admin_tab2:
            st.markdown("#### 📜 누적 전체 예약 히스토리")
            if os.path.exists(HISTORY_FILE):
                df_history = pd.read_csv(HISTORY_FILE)
                st.dataframe(df_history.iloc[::-1], use_container_width=True) # 최신순
                st.download_button("📥 기록 다운로드 (CSV)", data=df_history.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig'), file_name="bio_history.csv", mime="text/csv")
            else: st.info("아직 누적된 기록이 없습니다.")
