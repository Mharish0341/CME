import pandas as pd

# Load the Excel file
df = pd.read_excel('scraped_courses.xlsx')

# Fill NaN values
df['Faculty Name'] = df['Faculty Name'].fillna('N/A')
df['Faculty Qualification'] = df['Faculty Qualification'].fillna('N/A')


# Function to clean qualification
def clean_qual(qual):
    if qual == 'N/A':
        return 'N/A'
    qual = qual.replace('(opens in a new tab)', '').strip()
    qual = qual.replace('\n', ' ').strip()
    return qual


# Apply cleaning to Faculty Qualification
df['Faculty Qualification'] = df['Faculty Qualification'].apply(clean_qual)

# Now, check Faculty Name for any embedded qualifications (e.g., names like "Name, MD")
for idx in df.index:
    name = df.at[idx, 'Faculty Name']
    qual = df.at[idx, 'Faculty Qualification']

    if name == 'N/A':
        continue

    if ',' in name:
        # Split on the last comma to catch "First Last, MD"
        parts = name.rsplit(',', 1)
        new_name = parts[0].strip()
        add_qual = parts[1].strip() if len(parts) > 1 else ''

        if add_qual:
            # Append to existing qual
            if qual == 'N/A':
                new_qual = add_qual
            else:
                new_qual = add_qual + ', ' + qual
            df.at[idx, 'Faculty Qualification'] = new_qual
            df.at[idx, 'Faculty Name'] = new_name

# Save the updated DataFrame to a new Excel file
df.to_excel('Medpagetoday_activities.xlsx', index=False)

print("Updated Excel file saved as 'Medpagetoday_activities.xlsx'")