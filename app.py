import streamlit as st
import pandas as pd
import os
import urllib.parse
from datetime import datetime, timedelta

# 데이터 저장 파일명
DB_FILE = "reservations.csv"

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

def auto_cleanup_noshow(df):
    """예약 시작 15분이 지났는데 미입실인 예약을 자동 삭제합니다."""
    now = datetime.now()
    now_date = str(now.date())
    to_delete = []
    
    for idx, row in df.iterrows():
        if row["날짜"] == now_date and row["출석"] == "미입실":
            start_dt = datetime.strptime(f"{row['날짜']} {row['시작']}", "%Y-%m-%d %H:%M")
            # 15분 유예 시간 적용
            if now > (start_dt + timedelta(minutes=15)):
                to_delete.append(idx)
    
    if to_delete:
        df = df.drop(to_delete)
        df.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
    return df

def process_qr_checkin(df):
    """URL 쿼리 파라미터를 읽어 즉시 체크인 처리합니다."""
    # Streamlit의 신규 query_params API 사용
    q_params = st.query_params
    
    if "checkin" in q_params:
        room_code = q_params["checkin"]
        target_room = "1번 스터디룸" if room_code == "room1" else "2번 스터디룸"
        
        now = datetime.now()
        now_date = str(now.date())
        now_time = now.strftime("%H:%M")

        # 현재 시간대에 해당 방을 예약한 '미입실' 사용자 필터링
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
            # 중복 처리 방지를 위해 파라미터 초기화
            st.query_params.clear()
        else:
            st.warning(f"현재 {target_room}에 등록된 본인의 예약 시간이 아니거나 이미 인증되었습니다.")
    return df

# --- 초기 데이터 로드 및 자동 관리 실행 ---
df_all = get_latest_df()
df_all = auto_cleanup_noshow(df_all)
df_all = process_qr_checkin(df_all)

# --- 공통 설정 및 시간 ---
time_options = [f"{h:02d}:{m:02d}" for h in range(0, 24) for m in (0, 30)]
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
                if datetime.strptime(row["시작"], "%H:%M").time() <= now.time() < datetime.strptime(row["종료"], "%H:%M").time():
                    is_occ = True
                    status = "✅ 입실완료" if row["출석"] == "입실완료" else "⚠️ 미인증(곧 자동취소)"
                    st.error(f"{status} ({row['시작']}~{row['종료']})")
                    break
            if not is_occ: st.success("✅ 예약 가능")
    st.divider()
    st.caption("🌿 생명과학대학 학생회")

# --- 메인 화면 ---
st.title("🌿 생명과학대학 스터디룸 예약 시스템")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📅 예약 신청", "🔍 내 예약 확인", "📋 전체 일정 보기", "➕ 시간 연장", "♻️ 반납 및 취소"])

# [탭 1: 예약 신청]
with tab1:
    if now.minute < 30: d_start = now.replace(minute=30, second=0, microsecond=0)
    else: d_start = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    ds_str, de_str = d_start.strftime("%H:%M"), (d_start + timedelta(hours=1)).strftime("%H:%M")
    try: s_idx, e_idx = time_options.index(ds_str), time_options.index(de_str)
    except: s_idx, e_idx = 18, 20

    st.markdown('<div class="step-header">1. 예약자 정보 입력</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    dept = c1.selectbox("🏢 학과", dept_options, key="reg_dept")
    name = c2.text_input("👤 이름", placeholder="성함 입력", key="reg_name")
    sid = c3.text_input("🆔 학번", placeholder="학번 8자리", key="reg_sid")
    count = c4.number_input("👥 인원", min_value=1, max_value=20, value=1)

    st.markdown('<div class="step-header">2. 스터디룸 및 시간 선택</div>', unsafe_allow_html=True)
    sc1, sc2, sc3 = st.columns([2, 1, 1])
    room = sc1.selectbox("🚪 스터디룸 선택", ["1번 스터디룸", "2번 스터디룸"], key="reg_room")
    date = sc2.date_input("📅 날짜", min_value=now.date(), max_value=now.date()+timedelta(days=13), key="reg_date")
    tc1, tc2 = sc3.columns(2)
    st_t = tc1.selectbox("⏰ 시작", time_options, index=s_idx, key="reg_start")
    en_t = tc2.selectbox("⏰ 종료", time_options, index=e_idx, key="reg_end")

    if st.button("🚀 예약 신청하기"):
        if not (name.strip() and sid.strip()): st.error("정보를 모두 입력해 주세요.")
        elif any((df_all["이름"] == name.strip()) & (df_all["학번"] == str(sid.strip()))): st.error("🚫 이미 등록된 예약이 존재합니다.")
        elif st_t >= en_t: st.error("시간 설정 오류")
        elif check_overlap(date, st_t, en_t, room): st.error("❌ 이미 예약된 시간입니다.")
        else:
            pd.DataFrame([[dept, name.strip(), sid.strip(), count, str(date), st_t, en_t, room, "미입실"]], 
                         columns=["학과", "이름", "학번", "인원", "날짜", "시작", "종료", "방번호", "출석"]).to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False, encoding='utf-8-sig')
            
            st.info(f"🎉 예약 완료! {name}님, 이용 시 문 앞의 QR 코드를 찍어야 입실이 확정됩니다. (15분 경과 시 자동 취소)")
            st.rerun()

# [탭 2: 내 예약 확인]
with tab2:
    st.markdown('<div class="step-header">🔍 예약 확인 및 알림 설정</div>', unsafe_allow_html=True)
    mc1, mc2 = st.columns(2)
    m_name = mc1.text_input("조회용 이름", key="my_name")
    m_sid = mc2.text_input("조회용 학번", key="my_sid")
    if st.button("조회하기"):
        res = df_all[(df_all["이름"].astype(str).str.strip() == m_name.strip()) & (df_all["학번"].astype(str).str.strip() == m_sid.strip())]
        if not res.empty:
            r = res.iloc[0]
            st.markdown(f"""<div class="res-card"><h3>✅ {r['이름']}님의 예약</h3><p>📍 {r['방번호']} / 📅 {r['날짜']} / ⏰ {r['시작']} ~ {r['종료']}</p><p>상태: <b>{r['출석']}</b></p></div>""", unsafe_allow_html=True)
            # 캘린더 추가 링크 생략
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

# [탭 4, 5: 연장 및 반납]
with tab4:
    st.markdown('<div class="step-header">➕ 이용 시간 연장</div>', unsafe_allow_html=True)
    e_name = st.text_input("이름 (연장용)", key="e_n")
    if st.button("연장 가능 여부 확인"):
        df_e = get_latest_df()
        res_e = df_e[(df_e["이름"] == e_name) & (df_e["날짜"] == str(now.date()))]
        if not res_e.empty:
            target = res_e.iloc[-1]
            end_dt = datetime.combine(now.date(), datetime.strptime(target['종료'], "%H:%M").time())
            if (end_dt - timedelta(minutes=30)) <= now < end_dt:
                st.session_state['ext_target'] = target
                st.success(f"연장 가능! 현재 종료: {target['종료']}")
            else: st.warning("종료 30분 전부터 가능합니다.")
        else: st.warning("오늘 예약 내역 없음")
    if 'ext_target' in st.session_state:
        target = st.session_state['ext_target']
        new_en = st.selectbox("새 종료 시간", time_options[time_options.index(target['종료'])+1:time_options.index(target['종료'])+5])
        if st.button("연장 확정"):
            if check_overlap(now.date(), target['종료'], new_en, target['방번호']): st.error("중복 발생")
            else:
                df_up = get_latest_df()
                idx = df_up[(df_up["이름"] == e_name) & (df_up["날짜"] == str(now.date())) & (df_up["시작"] == target['시작'])].index
                df_up.loc[idx, "종료"] = new_en; df_up.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
                st.success("연장 완료!"); del st.session_state['ext_target']; st.rerun()

with tab5:
    st.markdown('<div class="step-header">♻️ 예약 반납 및 취소</div>', unsafe_allow_html=True)
    c_name = st.text_input("이름 (취소용)", key="c_n")
    if st.button("취소 내역 확인"):
        df_c = get_latest_df()
        res_c = df_c[df_c["이름"] == c_name].sort_values(by="날짜")
        if not res_c.empty:
            st.session_state['re_target'] = res_c.iloc[0]
            st.info(f"선택됨: {st.session_state['re_target']['날짜']} {st.session_state['re_target']['방번호']}")
    if 're_target' in st.session_state:
        if st.button("✅ 최종 취소/반납", type="primary"):
            df_del = get_latest_df(); t = st.session_state['re_target']
            df_del.drop(df_del[(df_del["이름"]==t["이름"]) & (df_del["학번"]==t["학번"]) & (df_del["날짜"]==t["날짜"]) & (df_del["시작"]==t["시작"])].index).to_csv(DB_FILE, index=False, encoding='utf-8-sig')
            st.success("취소 완료"); del st.session_state['re_target']; st.rerun()

# --- 관리자 메뉴 ---
st.markdown('<div class="spacer"></div>', unsafe_allow_html=True)
with st.expander("🛠️ 관리자 전용 메뉴"):
    pw = st.text_input("Admin Password", type="password")
    if pw == "bio1234":
        st.dataframe(df_all, use_container_width=True)
        if st.button("🗑️ 선택 삭제"):
            # 관리자용 개별 삭제 로직 구현 가능
            pass

