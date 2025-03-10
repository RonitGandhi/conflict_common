import streamlit as st
import fitz
from io import BytesIO
import pandas as pd
from fuzzywuzzy import fuzz  # For fuzzy string matching
import time  # To track execution time
import re  # For extracting years
import datetime

# Function to normalize publication titles
def clean_title(title):
    return " ".join(title.lower().strip().replace("-", " ").split())  # Normalize hyphens, spaces, and case

# Function to strip .pdf extension from file name
def clean_filename(file_name):
    return file_name.rsplit('.', 1)[0]  # Remove the .pdf extension

# Function to check if the text color is blue
def is_blue(color_int):
    r = (color_int >> 16) & 0xFF
    g = (color_int >> 8) & 0xFF
    b = color_int & 0xFF
    return b > r and b > g

# Function to extract titles and years from PDF
def extract_titles_and_years(file_object):
    titles_and_years = []

    if file_object is None or file_object.getbuffer().nbytes == 0:
        return []

    file_object.seek(0)
    pdf_document = fitz.open(stream=file_object.read(), filetype="pdf")

    try:
        for page_number in range(len(pdf_document)):
            page = pdf_document.load_page(page_number)
            current_title = ""
            current_year = ""
            for text_instance in page.get_text("dict")["blocks"]:
                if "lines" in text_instance:
                    for line in text_instance["lines"]:
                        for span in line["spans"]:
                            # Extract titles (blue text)
                            if is_blue(span['color']):
                                current_title += span['text'] + " "
                            else:
                                # Check if the text is a year (check for 4-digit number)
                                year_match = re.match(r"\b(19|20)\d{2}\b", span['text'])
                                if year_match:
                                    current_year = year_match.group(0)
                                    if current_title.strip() and current_year:
                                        titles_and_years.append((clean_title(current_title.strip()), current_year))
                                        current_title = ""  # Reset current title after saving
                                        current_year = ""  # Reset year after saving
    finally:
        pdf_document.close()

    return titles_and_years

# Function to find similar titles between two sets using fuzzy matching
def find_similar_titles(set1, set2, threshold=90):
    matches = set()
    for title1 in set1:
        for title2 in set2:
            if fuzz.ratio(title1, title2) >= threshold:
                matches.add(title1)  # Store only one version
    return matches

# Streamlit UI
st.title("ConflictMatch: Detecting conflicts through common publications")

# Add the attribution text below the title
st.markdown(
    '"This ConflictMatch tool is implemented based on the work done by Rohit Ramachandran, Rutgers University, NJ, USA"'
)

# Add instructions banner
st.markdown("""
### Instructions:
1. Upload at least 1 Google Scholar PDF in each group. Ensure all the papers are printed to PDF. See 'show more' bottom of google scholar link.
2. The algorithm will check for common publications across these group of researchers for different years selected and identify conflicts.
3. You can also view the tables showing common publications and corresponding conflicts.  
4. Once the analysis is complete, you can download the results as a CSV file.
""")


# Get the current year dynamically
current_year = datetime.datetime.now().year

# Dropdown for year filtering
year_options = ["All Years"] + list(range(current_year, 1950, -1))  # Start from current year
selected_years = st.multiselect("Select years to include:", year_options, default=year_options[1:6])  # Default: last 5 years

# If "All Years" is selected, include all years
if "All Years" in selected_years:
    selected_years = set(map(str, range(current_year, 1950, -1)))  # Convert all years to string
else:
    selected_years = set(map(str, [year for year in selected_years if year != "All Years"]))  # Convert selected years to string


# File uploader for Group 1 and Group 2
group1_files = st.file_uploader("Upload Google Scholar PDFs for Group 1", type=["pdf"], accept_multiple_files=True)
group2_files = st.file_uploader("Upload Google Scholar PDFs for Group 2", type=["pdf"], accept_multiple_files=True)

# Run simulation button
run_simulation_button = st.button("Run Simulation")

if run_simulation_button:
    # Record start time
    start_time = time.time()

    # Process Group 1 files
    group1_data = {}
    for file in group1_files:
        researcher_name = clean_filename(file.name)
        extracted_data = extract_titles_and_years(file)
        filtered_titles = {title for title, year in extracted_data if year in selected_years}
        group1_data[researcher_name] = filtered_titles

    # Process Group 2 files
    group2_data = {}
    for file in group2_files:
        researcher_name = clean_filename(file.name)
        extracted_data = extract_titles_and_years(file)
        filtered_titles = {title for title, year in extracted_data if year in selected_years}
        group2_data[researcher_name] = filtered_titles

    # Ensure we have data from both groups
    if group1_data and group2_data:
        st.subheader("Common Publications Between Researchers from Group 1 and Group 2")

        # Create a matrix for comparisons
        comparison_matrix = []
        group1_names = list(group1_data.keys())
        group2_names = list(group2_data.keys())

        for researcher1 in group1_names:
            row = []
            titles1 = group1_data[researcher1]
            for researcher2 in group2_names:
                titles2 = group2_data[researcher2]
                common_titles = find_similar_titles(titles1, titles2, threshold=90)
                row.append(len(common_titles))  # Store the number of common publications
            comparison_matrix.append(row)

        # Create the DataFrame for the matrix with filenames as labels
        df_comparisons = pd.DataFrame(comparison_matrix, index=[f"{i+1}. Grp 1: {name}" for i, name in enumerate(group1_names)], 
                                      columns=[f"Grp 2: {name}" for name in group2_names])

        # Display the comparison matrix with headers
        st.dataframe(df_comparisons.style.set_properties(**{'text-align': 'center', 'white-space': 'pre-wrap'}))

        # Convert to COI matrix
        df_coi = df_comparisons.applymap(lambda x: "COI" if x > 0 else "")

        # Style COI matrix
        def highlight_coi(val):
            return "background-color: #FFCCCC; font-weight: bold;" if val == "COI" else ""

        st.subheader("Conflict of Interest (COI) Matrix")
        st.dataframe(df_coi.style.applymap(highlight_coi))

        # Allow download of the CSV file
        @st.cache_data
        def convert_df(df):
            return df.to_csv(index=True).encode('utf-8')

        csv_data = convert_df(df_comparisons)
        st.download_button(
            label="Download Common publications as CSV",
            data=csv_data,
            file_name="publication_comparisons_matrix.csv",
            mime="text/csv"
        )

        # Table 2: Download COI Matrix CSV (df_coi)
        csv_data_coi = convert_df(df_coi)
        st.download_button(
        label="Download COI Matrix as CSV",
        data=csv_data_coi,
        file_name="publication_coi_matrix.csv",
        mime="text/csv"
        )

    # Record end time and compute total simulation time
    end_time = time.time()
    total_time = (end_time - start_time) / 60  # Convert seconds to minutes

    # Display the total simulation time
    st.subheader(f"Total simulation time: {total_time:.2f} minutes")
