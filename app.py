import streamlit as st
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
        return pd.DataFrame(columns=["학과", "이름", "학번", "인원", "날짜", "시작", "종료", "방번호", "출석", "팀원학번"])
    df = pd.read_csv(DB_FILE)
    if "출석" not in df.columns:
        df["출석"] = "미입실"
    if "팀원학번" not in df.columns:
        df["팀원학번"] = ""
    for col in ["이름", "학번", "날짜", "시작", "종료", "방번호", "팀원학번"]:
        df[col] = df[col].astype(str).str.strip()
    return df

def check_team_duplication(member_ids, target_date):
    """대표자 및 팀원 중 한 명이라도 해당 날짜에 이미 예약이 있는지 전수 검사합니다."""
    df = get_latest_df()
    if df.empty: return False, ""
    day_df = df[df["날짜"] == str(target_date)]
    for m_id in member_ids:
        if not m_id: continue
        is_booked = day_df[(day_df["학번"] == m_id) | (day_df["팀원학번"].str.contains(m_id, na=False))]
        if not is_booked.empty:
            return True, m_id
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
    .stButton>button { background-color: var(--point-color); color: white; border-radius: 10px; font-weight: bold; border: none; width: 100%; height: 3.2rem; }
    .stButton>button:disabled { background-color: #E0E0E0 !important; color: #9E9E9E !important; cursor: not-allowed !important; }
    .schedule-card, .res-card { padding: 15px; border-radius: 12px; border-left: 6px solid var(--point-color); background-color: rgba(167, 215, 197, 0.1); margin-bottom: 12px; }
    .step-header { color: var(--point-dark); font-weight: bold; border-bottom: 2px solid var(--point-color); padding-bottom: 5px; margin-bottom: 15px; font-size: 1.1rem; }
    .success-receipt { border: 2px dashed var(--point-color); padding: 25px; border-radius: 15px; margin-top: 20px; background-color: white; color: black; }
    .receipt-title { color: var(--point-color); font-size: 1.5rem; font-weight: bold; text-align: center; margin-bottom: 20px; }
    .receipt-item { display: flex; justify-content: space-between; margin-bottom: 10px; border-bottom: 1px solid rgba(167, 215, 197, 0.3); padding-bottom: 5px; }
    </style>
    """, unsafe_allow_html=True)

now_kst = get_kst_now().replace(tzinfo=None)
current_time_str = now_kst.strftime("%H:%M")
time_options_all = [f"{h:02d}:{m:02d}" for h in range(0, 24) for m in (0, 30)]
depts = ["스마트팜과학과", "식품생명공학과", "유전생명공학과", "융합바이오·신소재공학과"]

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
                st.markdown(f'<div style="margin-bottom: -15px;"><h3 style="color:{status_color}; margin-bottom: 5px;">{"현재 이용 중" if current_user["출석"] == "입실완료" else "인증 대기 중"}</h3><p style="font-size: 1.1rem; font-weight: bold;">⏰ 종료 예정 시각: <span style="background-color: #f0f2f6; padding: 2px 5px; border-radius: 4px; color: black;">{current_user["종료"]}</span></p></div>', unsafe_allow_html=True)
                if current_user["출석"] == "미입실": st.warning("⚠️ 15분 내 QR 인증 필요")
                st.divider()
            else: st.success("현재 비어 있음")
            next_res = room_today[room_today["시작"] > current_time_str]
            st.markdown("<p style='font-size: 0.9rem; font-weight: bold; margin-bottom: 5px;'>📅 다음 예약 안내</p>", unsafe_allow_html=True)
            if not next_res.empty:
                for _, row in next_res.iterrows(): st.caption(f"🕒 {row['시작']} ~ {row['종료']} (예약 완료)")
            else: st.caption("이후 예정된 예약이 없습니다.")

# --- [4. 메인 화면 구성] ---
st.title("생명과학대학 스터디룸 예약")
tabs = st.tabs(["📅 예약 신청", "🔍 내 예약 확인", "📋 전체 예약 일정", "➕ 시간 연장", "♻️ 반납 및 취소"])

with tabs[0]:
    if 'reserve_success' not in st.session_state:
        st.session_state.reserve_success = False
        st.session_state.last_res = {}
    
    if not st.session_state.reserve_success:
        st.markdown('<div class="step-header">1. 이용 인원 및 구성원 정보 입력</div>', unsafe_allow_html=True)
        
        # 가로폭을 줄이기 위해 컬럼 분할
        ic1, ic2 = st.columns([1, 2])
        total_count = ic1.selectbox("이용 인원", [3, 4, 5, 6], key="reg_count")
        
        st.write("**👤 대표자**")
        rc1, rc2, rc3 = st.columns([1.5, 1.2, 1])
        rep_dept = rc1.selectbox("학과", depts, key="rep_dept", label_visibility="collapsed")
        rep_name = rc2.text_input("이름", key="rep_name", placeholder="이름", label_visibility="collapsed")
        rep_id = rc3.text_input("학번", key="rep_id", max_chars=10, placeholder="학번", label_visibility="collapsed")

        st.write(f"**👥 구성원 ({total_count-1}명)**")
        member_names, member_ids = [], []
        for i in range(total_count - 1):
            mc1, mc2, mc3 = st.columns([1.5, 1.2, 1])
            m_dept = mc1.selectbox(f"학과{i}", depts, key=f"m_dept_{i}", label_visibility="collapsed")
            m_name = mc2.text_input(f"이름{i}", key=f"m_n_{i}", placeholder="이름", label_visibility="collapsed")
            m_id = mc3.text_input(f"학번{i}", key=f"m_id_{i}", max_chars=10, placeholder="학번", label_visibility="collapsed")
            member_names.append(m_name.strip()); member_ids.append(m_id.strip())

        st.markdown('<div class="step-header">2. 예약 날짜/장소/시간 선택</div>', unsafe_allow_html=True)
        sc1, sc2, tc1, tc2 = st.columns([1.2, 1.2, 1, 1])
        
        room = sc1.selectbox("🚪 장소", ["1번 스터디룸", "2번 스터디룸"], key="reg_room")
        date_options = [now_kst.date(), (now_kst + timedelta(days=1)).date()]
        sel_date = sc2.selectbox("📅 날짜", date_options, format_func=lambda x: x.strftime("%Y-%m-%d"), key="reg_date")
        
        threshold_time = (now_kst - timedelta(minutes=15)).strftime("%H:%M")
        available_start = [t for t in time_options_all if t >= threshold_time] if str(sel_date) == str(now_kst.date()) else time_options_all
        st_t = tc1.selectbox("⏰ 시작", available_start, key="reg_start")
        en_t = tc2.selectbox("⏰ 종료", [t for t in time_options_all if t > st_t], key="reg_end")

        all_ids = [rep_id.strip()] + member_ids
        id_to_name = {rep_id.strip(): rep_name.strip()}
        for m_id, m_name in zip(member_ids, member_names):
            id_to_name[m_id] = m_name

        is_ready = rep_name and len(rep_id)==10 and all(member_names) and all(len(idx)==10 for idx in all_ids)
        
        if st.button("🚀 예약 신청하기", key="btn_reservation", disabled=not is_ready):
            duration = datetime.strptime(en_t, "%H:%M") - datetime.strptime(st_t, "%H:%M")
            duplicate_found, culprit_id = check_team_duplication(all_ids, sel_date)
            
            if duration > timedelta(hours=3): st.error("🚫 최대 이용 가능 시간은 3시간입니다.")
            elif duplicate_found:
                culprit_name = id_to_name.get(culprit_id, culprit_id)
                st.error(f"❌ 예약 실패: '{culprit_name}'님은 해당 날짜에 이미 예약 내역이 있습니다. (1인 1일 1회 제한)")
            elif check_overlap(sel_date, st_t, en_t, room): st.error("❌ 이미 예약된 시간입니다.")
            else:
                new_data = [rep_dept, rep_name.strip(), rep_id.strip(), total_count, str(sel_date), st_t, en_t, room, "미입실", ",".join(member_ids)]
                pd.DataFrame([new_data], columns=df_all.columns).to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False, encoding='utf-8-sig')
                st.session_state.reserve_success = True
                st.session_state.last_res = {"name": rep_name, "sid": rep_id, "room": room, "date": str(sel_date), "start": st_t, "end": en_t}
                st.rerun()
    else:
        res = st.session_state.last_res
        st.success("🎉 예약이 완료되었습니다!")
        st.markdown(f'<div class="success-receipt"><div class="receipt-title">🌿 예약 확인서</div><div class="receipt-item"><span>신청자</span><b>{res["name"]} ({res["sid"]})</b></div><div class="receipt-item"><span>장소</span><b style="color: var(--point-color);">{res["room"]}</b></div><div class="receipt-item"><span>시간</span><b>{res["date"]} / {res["start"]} ~ {res["end"]}</b></div></div>', unsafe_allow_html=True)
        if st.button("처음으로 돌아가기"): st.session_state.reserve_success = False; st.rerun()

with tabs[1]:
    st.markdown('<div class="step-header">🔍 내 예약 내역 확인</div>', unsafe_allow_html=True)
    mc1, mc2 = st.columns(2)
    m_n = mc1.text_input("구성원 이름", key="lookup_n")
    m_s = mc2.text_input("구성원 학번 (10자리)", key="lookup_s", max_chars=10)
    if st.button("조회하기", key="btn_lookup"):
        df_curr = get_latest_df()
        res_list = df_curr[((df_curr["이름"] == m_n.strip()) & (df_curr["학번"] == m_s.strip())) | (df_curr["팀원학번"].str.contains(m_s.strip(), na=False))]
        if not res_list.empty:
            for _, r in res_list.iterrows(): st.markdown(f'<div class="res-card">📍 {r["방번호"]} | {r["날짜"]} | ⏰ {r["시작"]}~{r["종료"]} | 상태: {r["출석"]}</div>', unsafe_allow_html=True)
        else: st.error("조회된 예약 내역이 없습니다.")

with tabs[2]:
    df_v = get_latest_df()
    if not df_v.empty:
        s_date = st.selectbox("날짜 선택", sorted(df_v["날짜"].unique()), key="view_date")
        day_df = df_v[df_v["날짜"] == s_date].sort_values(by=["방번호", "시작"])
        for r_n in ["1번 스터디룸", "2번 스터디룸"]:
            st.markdown(f"#### 🚪 {r_n}")
            room_day = day_df[day_df["방번호"] == r_n]
            if room_day.empty: st.caption("해당 날짜에 예약이 없습니다.")
            else:
                for _, row in room_day.iterrows(): st.markdown(f'<div class="schedule-card"><b>{row["시작"]}~{row["종료"]}</b> | 예약완료</div>', unsafe_allow_html=True)
    else: st.info("현재 등록된 예약 내역이 없습니다.")

with tabs[3]:
    st.markdown('<div class="step-header">➕ 이용 시간 연장</div>', unsafe_allow_html=True)
    ec1, ec2 = st.columns(2)
    ext_n = ec1.text_input("구성원 이름", key="ext_n_input")
    ext_id = ec2.text_input("구성원 학번 (10자리)", key="ext_id_input", max_chars=10)
    
    if st.button("연장 가능 여부 확인", key="btn_ext_check"):
        df_e = get_latest_df()
        # [수정] 이름과 학번 모두 체크하며, 구성원인 경우도 포함
        res_e = df_e[((df_e["학번"] == ext_id.strip()) | (df_e["팀원학번"].str.contains(ext_id.strip(), na=False))) & (df_e["날짜"] == str(now_kst.date()))]
        if not res_e.empty:
            target = res_e.iloc[-1]
            if target["출석"] != "입실완료": st.error("🚫 QR 인증 후에만 연장이 가능합니다.")
            else:
                end_dt = datetime.combine(now_kst.date(), datetime.strptime(target['종료'], "%H:%M").time())
                if (end_dt - timedelta(minutes=30)) <= now_kst < end_dt:
                    st.session_state['ext_target'] = target; st.success(f"✅ 연장 가능 (현재 종료 시각: {target['종료']})")
                else: st.warning("⚠️ 이용 종료 30분 전부터만 연장 신청이 가능합니다.")
        else: st.error("🔍 오늘 예약 내역을 찾을 수 없습니다.")

    if 'ext_target' in st.session_state:
        target = st.session_state['ext_target']
        df_f = get_latest_df()
        next_res = df_f[(df_f["방번호"] == target["방번호"]) & (df_f["날짜"] == target["날짜"]) & (df_f["시작"] >= target["종료"])].sort_values(by="시작")
        limit_t = next_res.iloc[0]["시작"] if not next_res.empty else "23:59"
        limit_dt = datetime.strptime(limit_t, "%H:%M")
        curr_en_dt = datetime.strptime(target['종료'], "%H:%M")
        opts = [(curr_en_dt + timedelta(minutes=30*i)).strftime("%H:%M") for i in range(1, 5) if (curr_en_dt + timedelta(minutes=30*i)).time() <= limit_dt.time()]
        if not opts: st.error(f"❌ 다음 예약 일정으로 인해 더 이상 연장이 불가합니다.")
        else:
            new_en = st.selectbox("새로운 종료 시각 선택", opts, key="ext_sel_box")
            if st.button("최종 연장 확정", key="btn_ext_confirm"):
                df_up = get_latest_df()
                idx = df_up[(df_up["날짜"] == target["날짜"]) & (df_up["방번호"] == target["방번호"]) & (df_up["시작"] == target["시작"])].index
                df_up.loc[idx, "종료"] = new_en
                df_up.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
                st.success(f"연장 완료! ({new_en})"); del st.session_state['ext_target']; st.rerun()

with tabs[4]:
    st.markdown('<div class="step-header">♻️ 예약 반납 및 취소</div>', unsafe_allow_html=True)
    cc1, cc2 = st.columns(2)
    can_n = cc1.text_input("구성원 이름", key="can_n_input")
    can_id = cc2.text_input("구성원 학번 (10자리)", key="can_id_input", max_chars=10)
    
    if st.button("내 예약 찾기", key="btn_can_lookup"):
        df_c = get_latest_df()
        res_c = df_c[(df_c["학번"] == can_id.strip()) | (df_c["팀원학번"].str.contains(can_id.strip(), na=False))]
        if not res_c.empty: st.session_state['cancel_list'] = res_c
        else: st.error("🔍 예약 내역이 없습니다.")
    if 'cancel_list' in st.session_state:
        opts = [f"{r['날짜']} | {r['방번호']} ({r['시작']}~{r['종료']})" for _, r in st.session_state['cancel_list'].iterrows()]
        target_idx = st.selectbox("처리할 내역 선택", range(len(opts)), format_func=lambda x: opts[x])
        if st.button("최종 취소/반납 수행"):
            t = st.session_state['cancel_list'].iloc[target_idx]
            df_final = get_latest_df().drop(get_latest_df()[(get_latest_df()["날짜"] == t["날짜"]) & (get_latest_df()["방번호"] == t["방번호"]) & (get_latest_df()["시작"] == t["시작"])].index)
            df_final.to_csv(DB_FILE, index=False, encoding='utf-8-sig'); del st.session_state['cancel_list']; st.rerun()

st.markdown('<div style="height:100px;"></div>', unsafe_allow_html=True)
with st.expander("🛠️ 관리자 전용 메뉴"):
    pw = st.text_input("관리자 비밀번호", type="password", key="admin_pw")
    if pw == "bio1234":
        # 탭을 나누어 실시간 예약과 누적 히스토리 구분
        admin_tab1, admin_tab2 = st.tabs(["📝 실시간 예약 관리", "📜 누적 전체 기록"])

        with admin_tab1:
            st.markdown("#### 📍 현재 활성 예약 목록")
            df_ad = get_latest_df()
            if not df_ad.empty:
                st.dataframe(df_ad, use_container_width=True)
                labels = [f"{r['이름']} | {r['날짜']} | {r['시작']} ({r['방번호']})" for _, r in df_ad.iterrows()]
                sel = st.selectbox("삭제 대상을 선택하세요", range(len(labels)), format_func=lambda x: labels[x])
                if st.button("강제 삭제"):
                    t = df_ad.iloc[sel]
                    df_final = get_latest_df().drop(df_ad[(df_ad["날짜"] == t["날짜"]) & (df_ad["방번호"] == t["방번호"]) & (df_ad["시작"] == t["시작"])].index)
                    df_final.to_csv(DB_FILE, index=False, encoding='utf-8-sig'); st.rerun()
            else: st.info("활성 예약 없음")

        with admin_tab2:
            st.markdown("#### 📜 전체 예약 히스토리 (과거 기록 포함)")
            if os.path.exists(HISTORY_FILE):
                df_history = pd.read_csv(HISTORY_FILE)
                # 최신순 정렬
                st.dataframe(df_history.iloc[::-1], use_container_width=True)
                csv = df_history.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
                st.download_button("📥 전체 기록 다운로드 (CSV)", data=csv, file_name="bio_studyroom_history.csv", mime="text/csv")
            else: st.info("누적 기록이 아직 없습니다.")










