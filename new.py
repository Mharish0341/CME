import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

@st.cache_data
def load_data():
    df = pd.read_excel('processed_mycme.xlsx')
    return df

df = load_data()

df['course_release_date'] = pd.to_datetime(df['course_release_date'], errors='coerce')
df['course_expires_date'] = pd.to_datetime(df['course_expires_date'], errors='coerce')

today = pd.Timestamp.today().normalize()

# Identify active courses
df['Is Active Course'] = df['course_expires_date'] >= today

# Group by faculty and compute total vs. active
faculty_summary = df.groupby('Faculty Name').agg(
    Total_Courses=('course_expires_date', 'count'),
    Active_Courses=('Is Active Course', 'sum')
).reset_index()

# Create a "Still Continuing" indicator if faculty has at least 1 active course
faculty_summary['Still Continuing?'] = faculty_summary['Active_Courses'] > 0

st.title("Faculty Continuing CME Dashboard")

st.markdown("""
This dashboard focuses on faculty members and whether they are **still continuing** their CME 
(i.e., they have at least one course with an expiration date on or after today).
""")

st.markdown("### Summary of All Faculty")
st.write("Total Faculty:", faculty_summary['Faculty Name'].nunique())
st.write("Faculty Still Continuing:", faculty_summary['Still Continuing?'].sum())

# Bar chart of Active Courses by Faculty
fig = px.bar(
    faculty_summary,
    x='Faculty Name',
    y='Active_Courses',
    title='Active Courses per Faculty (All)',
    labels={'Faculty Name': 'Faculty', 'Active_Courses': 'Count of Active Courses'}
)
fig.update_layout(xaxis_tickangle=-45)
st.plotly_chart(fig)

st.markdown("### Detailed Faculty View")

# Add an "All" option to easily show everyone
all_faculty = ["All"] + list(sorted(faculty_summary['Faculty Name'].unique()))
chosen_faculty = st.multiselect(
    "Select Faculty (choose one or many, or 'All' to show everyone):",
    options=all_faculty,
    default=["All"]
)

if "All" in chosen_faculty or len(chosen_faculty) == 0:
    filtered_faculty = faculty_summary
else:
    filtered_faculty = faculty_summary[faculty_summary['Faculty Name'].isin(chosen_faculty)]

st.write("### Filtered Faculty Summary")
st.dataframe(filtered_faculty)

st.write("""
Below is a table of all **faculty details** from the dataset, filtered for the selected faculty 
(but **including all their courses**, whether active or not). 
""")

# Filter the original DataFrame (df) by selected faculty
if "All" in chosen_faculty or len(chosen_faculty) == 0:
    df_filtered = df
else:
    df_filtered = df[df['Faculty Name'].isin(chosen_faculty)]

st.dataframe(df_filtered[[
    'Faculty Name',
    'Degree',
    'Faculty Bio',
    'Professional Roles',
    'Course Title',
    'course_release_date',
    'course_expires_date',
    'course_credits',
    'Source Link'
]])

st.markdown("### End of Dashboard")
