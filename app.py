import streamlit as st
from streamlit.logger import get_logger
from st_keyup import st_keyup
import requests
import json
import pandas as pd
from datetime import time

st.set_page_config(page_title="Cheese Strainer", layout="wide")

# Initialize logger
logger = get_logger(__name__)

SEMESTERS = [
    ("2026-27 Winter", 2026, 200),
    ("OLD 2025-25 Spring", 2025, 201),
    ("OLD 2025-26 Winter", 2025, 200),
]

DAY_TO_HEBREW = {
    "Sunday": "ראשון",
    "Monday": "שני",
    "Tuesday": "שלישי",
    "Wednesday": "רביעי",
    "Thursday": "חמישי",
}

WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"]
URL_TEMPLATE = "https://sap.cheesefork.cf/courses_{}_{}.min.js"


def parse_time(t_str):
    parts = t_str.split(" - ")
    sh, sm = map(int, parts[0].strip().split(":"))
    eh, em = map(int, parts[1].strip().split(":"))
    return sh * 60 + sm, eh * 60 + em


@st.cache_data(ttl="12h", show_spinner="Loading semester data")    
def fetch_semester(year, sem):
    url = URL_TEMPLATE.format(year, sem)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    text = resp.text.strip()
    logger.debug(f"text size after strip is: {len(text)}")
    prefix = "var courses_from_rishum = "
    if text.startswith(prefix):
        text = text[len(prefix):]
    if text.endswith(";"):
        text = text[:-1]
    text = text[text.find('['):text.rfind(']')+1]
    logger.info(f"text size post filtering is: {len(text)}")
    return json.loads(text)


def build_occupancy(data):
    occupied = []
    rooms = set()
    for course in data:
        for entry in course.get("schedule", []):
            day = entry.get("יום")
            time_str = entry.get("שעה")
            building = entry.get("בניין", "").strip()
            room = entry.get("חדר")
            if not day or not time_str or not building or room is None:
                continue
            start_min, end_min = parse_time(time_str)
            occupied.append((day, building, str(room), start_min, end_min))
            rooms.add((building, str(room)))
    return occupied, rooms


def find_free(occupied, rooms, day_str, q_start, q_end):
    day_he = DAY_TO_HEBREW.get(day_str)
    if not day_he:
        return []
    busy = set()
    for d, bld, rm, occ_s, occ_e in occupied:
        if d == day_he and occ_s < q_end and occ_e > q_start:
            busy.add((bld, rm))
    return sorted(rooms - busy, key=lambda x: (x[0], x[1]))


st.title("Cheese Strainer")
st.markdown("Find free rooms at the Technion")

sem_label = st.selectbox("Semester", [s[0] for s in SEMESTERS])
sem = next(s for s in SEMESTERS if s[0] == sem_label)

# This caches the build_occupancy as well - so we will keep it even though fetch_semester 
# is caching requests
if "cache_key" not in st.session_state or st.session_state.cache_key != sem:
    with st.spinner("Loading semester data..."):
        try:
            raw = fetch_semester(sem[1], sem[2])
            occ, rooms = build_occupancy(raw)
            st.session_state.occupied = occ
            st.session_state.rooms = rooms
            st.session_state.cache_key = sem
            st.success(f"Loaded — {len(rooms)} rooms, {len(occ)} schedule entries")
        except Exception as e:
            st.error(f"Failed to load data: {e}")
            st.stop()

occupied = st.session_state.occupied
rooms = st.session_state.rooms

col1, col2, col3 = st.columns(3)
with col1:
    day = st.selectbox("Day", WEEKDAYS)
with col2:
    start_t = st.time_input("Start time", time(10, 0))
with col3:
    end_t = st.time_input("End time", time(11, 0))

if start_t >= end_t:
    st.warning("End time must be after start time")
else:
    q_start = start_t.hour * 60 + start_t.minute
    q_end = end_t.hour * 60 + end_t.minute
    free = find_free(occupied, rooms, day, q_start, q_end)

    st.subheader(f"Free Rooms — {day} ({start_t.strftime('%H:%M')}–{end_t.strftime('%H:%M')})")


    if free:
        df = pd.DataFrame(free, columns=["Building", "Room"])
        @st.fragment
        def dataframe_disp():
            search_query = st_keyup("Filter table")
            filtered_df = df[ df['Building'].str.contains(search_query, case=False, na=False) | 
                        df['Room'].str.contains(search_query, case=False, na=False)]
            st.dataframe(filtered_df, width="stretch", hide_index=True)
        dataframe_disp()
        st.caption(f"{len(free)} free rooms")
    else:
        st.info("No free rooms found for this time slot")
