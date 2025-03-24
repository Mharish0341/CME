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
df['Is Active Course'] = df['course_expires_date'] >= today

faculty_summary = df.groupby('Faculty Name').agg(
    Total_Courses=('course_expires_date', 'count'),
    Active_Courses=('Is Active Course', 'sum')
).reset_index()
faculty_summary['Inactive_Courses'] = faculty_summary['Total_Courses'] - faculty_summary['Active_Courses']
faculty_summary['Still Continuing?'] = faculty_summary['Active_Courses'] > 0

st.title("Faculty Continuing CME Dashboard")

st.markdown("""
This dashboard shows faculty members and whether they are **still continuing** their CME 
(i.e., at least one course with an expiration date on or after today).
""")

st.markdown("### Overall Faculty Stats")
st.write("Total Faculty:", faculty_summary['Faculty Name'].nunique())
st.write("Faculty Still Continuing:", faculty_summary['Still Continuing?'].sum())

all_faculty = ["All"] + sorted(faculty_summary['Faculty Name'].unique())
chosen_faculty = st.multiselect(
    "Select Faculty (choose one or many, or 'All' to show everyone):",
    options=all_faculty,
    default=["All"]
)

if "All" in chosen_faculty or len(chosen_faculty) == 0:
    filtered_summary = faculty_summary
    df_filtered = df
else:
    filtered_summary = faculty_summary[faculty_summary['Faculty Name'].isin(chosen_faculty)]
    df_filtered = df[df['Faculty Name'].isin(chosen_faculty)]

fig = px.bar(
    filtered_summary,
    x='Active_Courses',
    y='Faculty Name',
    orientation='h',
    title='Active Courses per Selected Faculty',
    labels={'Active_Courses': 'Active Courses', 'Faculty Name': 'Faculty'}
)
fig.update_yaxes(autorange='reversed')
st.plotly_chart(fig)

st.markdown("### Filtered Faculty Summary")
st.dataframe(filtered_summary)

st.write("""
Below are two separate tables for **Active** and **Inactive** courses among the selected faculty.
""")

# Split the filtered data into active vs. inactive
active_filtered = df_filtered[df_filtered['course_expires_date'] >= today]
inactive_filtered = df_filtered[df_filtered['course_expires_date'] < today]

st.markdown("### Active Courses for Selected Faculty")
st.dataframe(active_filtered[[
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

st.markdown("### Inactive Courses for Selected Faculty")
st.dataframe(inactive_filtered[[
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

