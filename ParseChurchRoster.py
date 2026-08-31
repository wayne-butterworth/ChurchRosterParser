## v1 from Google AI


import argparse
from datetime import datetime
import os
import re
from ics import Calendar, Event
import pdfplumber

# for debug printing
from pprint import pprint

from backports.zoneinfo import ZoneInfo


def parse_pdf_roster(pdf_path, target_name):
    extracted_events = []
    
    # Complete list of expected columns
    known_headers = [
        "Date", "Time", "Service Leader", "Reader", "Prayers", 
        "Communion Assistant", "Welcomer", "Hospitality", "Backbone"
    ]

    # Timezone for calendar entries
    local_tz = ZoneInfo("Australia/Sydney")

    with pdfplumber.open(pdf_path) as pdf:
        pprint(f"Opened PDF '{pdf_path}' with {len(pdf.pages)} pages.")
        for page_num, page in enumerate(pdf.pages, 1):
            words = page.extract_words(
                x_tolerance=3, 
                y_tolerance=3, 
                keep_blank_chars=False
            )
            
            if not words:
                pprint(f"Page {page_num}: No words found.")
                continue

            # Group individual word tokens into text lines based on vertical 'top' coordinate
            lines_dict = {}
            for w in words:
                y_key = round(w["top"], 1)
                matched_y = None
                for existing_y in lines_dict.keys():
                    if abs(existing_y - y_key) <= 3.0:  # Expanded tolerance for slightly wavy printing
                        matched_y = existing_y
                        break
                
                if matched_y is None:
                    matched_y = y_key
                    lines_dict[matched_y] = []
                    
                lines_dict[matched_y].append(w)

            sorted_y_levels = sorted(lines_dict.keys())
            
            # Reconstruct lines as strings while tracking horizontal segments
            structured_rows = []
            header_row_idx = -1
            header_x_positions = []
            
            for idx, y in enumerate(sorted_y_levels):
                line_words = sorted(lines_dict[y], key=lambda w: w["x0"])
                
                segments = []
                if line_words:
                    current_seg = line_words[0].copy()
                    current_text = current_seg["text"]
                    
                    for nw in line_words[1:]:
                        # If words are visually close, join them (helps multi-word headers like "Service Leader")
                        if nw["x0"] - current_seg["x1"] < 12:  # Increased gap threshold
                            current_text += " " + nw["text"]
                            current_seg["x1"] = nw["x1"]
                            current_seg["text"] = current_text
                        else:
                            segments.append(current_seg)
                            current_seg = nw.copy()
                            current_text = nw["text"]
                    segments.append(current_seg)

                structured_rows.append(segments)
                
                # REVISED HEADER DETECTION: Score the row by matching known keywords
                full_line_text = " ".join([s["text"] for s in segments]).lower()
                matched_count = sum(1 for h in known_headers if h.lower() in full_line_text)
                
                # If a line contains 3 or more of your roster titles, it's definitely the header row
                if matched_count >= 3 and header_row_idx == -1:
                    header_row_idx = idx
                    header_x_positions = segments

            if header_row_idx == -1:
                print(f"[Warning] Skipping Page {page_num}: Couldn't identify the roster header row.")
                continue

            # Clean and map headers dynamically from text coordinates found
            headers = [s["text"].strip() for s in header_x_positions]
            
            # Map data rows below the discovered header
            raw_rows = []
            for segments in structured_rows[header_row_idx + 1:]:
                if not segments:
                    continue
                    
                row_data = {h: "" for h in headers}
                
                for seg in segments:
                    seg_mid = (seg["x0"] + seg["x1"]) / 2
                    
                    best_header = None
                    min_distance = float("inf")
                    
                    # Find which header column this piece of text aligns under vertically
                    for h_seg in header_x_positions:
                        h_mid = (h_seg["x0"] + h_seg["x1"]) / 2
                        dist = abs(seg_mid - h_mid)
                        if dist < min_distance:
                            min_distance = dist
                            best_header = h_seg["text"].strip()
                    
                    # Store text under its structural column header
                    if best_header and min_distance < 75:  
                        # Append text if multiple rows sit close together
                        if row_data[best_header]:
                            row_data[best_header] += " " + seg["text"].strip()
                        else:
                            row_data[best_header] = seg["text"].strip()

                if not any(row_data.values()):
                    pprint(f"Page {page_num}: Skipping blank row.")
                    continue
                raw_rows.append(row_data)

            pprint("Page {}: Raw rows:".format(page_num))
            pprint(raw_rows)  # Debug: Print the cleaned and filled rows for verification
            
            # Clean up and propagate dates/times across multi-row allocations
            # There are 3 rows per service, but only the middle row has the date/time. 
            
            # Forward pass, the get the missing rows below the date/time row
            pprint("Fill missing dates, forward pass")
            current_date = None
            current_time = None
            
            for i in range(len(raw_rows)):
                if raw_rows[i].get("Date"):
                    current_date = raw_rows[i]["Date"]
                if raw_rows[i].get("Time"):
                    current_time = raw_rows[i]["Time"]
                pprint(f"Row {i} - Date: {raw_rows[i].get('Date')}")
            
                if not raw_rows[i].get("Date") and current_date:
                    pprint(f"Row {i} - Filling missing Date with: {current_date}")
                    raw_rows[i]["Date"] = current_date
                    current_date = None  # Reset after filling to avoid overwriting future rows
                if not raw_rows[i].get("Time") and current_time:
                    raw_rows[i]["Time"] = current_time
                    current_time = None  # Reset after filling to avoid overwriting future rows

            # Reverse pass, to fill the missing rows above the date/time row
            pprint("Fill missing dates, reverse pass")
            current_date = None
            current_time = None
            
            for i in reversed(range(len(raw_rows))):
                if raw_rows[i].get("Date"):
                    current_date = raw_rows[i]["Date"]
                if raw_rows[i].get("Time"):
                    current_time = raw_rows[i]["Time"]
                pprint(f"Row {i} - Date: {raw_rows[i].get('Date')}")

                if not raw_rows[i].get("Date") and current_date:
                    pprint(f"Row {i} - Filling missing Date with: {current_date}")
                    raw_rows[i]["Date"] = current_date
                    current_date = None  # Reset after filling to avoid overwriting future rows
                if not raw_rows[i].get("Time") and current_time:
                    raw_rows[i]["Time"] = current_time
                    current_time = None  # Reset after filling to avoid overwriting future rows

            pprint(f"Page {page_num}: Cleaned and filled rows:")
            pprint(raw_rows)  # Debug: Print the cleaned and filled rows for verification

            # Filter and process rows matching the target name
            for row in raw_rows:
                date_key = next((k for k in row if "date" in k.lower()), None)
                time_key = next((k for k in row if "time" in k.lower()), None)
                
                date_val = row.get(date_key) if date_key else None
                time_val = row.get(time_key) if time_key else None

                if not date_val or not time_val:
                    pprint(f"Page {page_num}: Skipping row due to missing Date or Time: {row}")
                    continue

                # Regex fallbacks to extract structured elements safely
                date_match = re.search(r"\b\d{1,2}/\d{1,2}/\d{4}\b", date_val)
                if not date_match:
                    continue
                date_clean = date_match.group(0)

                time_clean = time_val.lower().replace(" ", "")
                time_match = re.search(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", time_clean)
                if not time_match:
                    continue
                time_clean = time_match.group(0)

                # Parse operational date times
                try:
                    if "am" in time_clean:
                        t_str = time_clean.replace("am", "")
                        hour = int(t_str.split(":")) if ":" in t_str else int(t_str)
                        minute = int(t_str.split(":")) if ":" in t_str else 0
                    elif "pm" in time_clean:
                        t_str = time_clean.replace("pm", "")
                        hour = int(t_str.split(":")) + 12 if ":" in t_str else int(t_str) + 12
                        if hour == 24:
                            hour = 12
                        minute = int(t_str.split(":")) if ":" in t_str else 0
                    else:
                        continue

                    start_dt = datetime.strptime(date_clean, "%d/%m/%Y").replace(hour=hour, minute=minute, tzinfo=local_tz)
                    end_dt = start_dt.replace(hour=start_dt.hour + 1)
                except Exception:
                    pprint(f"Page {page_num}: Error parsing date/time for row: {row}")
                    continue

                # Run target match assignment scan across distinct column mappings
                for role, person in row.items():
                    if "date" in role.lower() or "time" in role.lower() or not person:
                        continue

                    if target_name.lower() in person.lower():
                        updated=False
                        for event in extracted_events:
                            if event["start"] == start_dt:
                                # If you already have a job, add this to it
                                event["summary"] += f", {role}"
                                event["description"] += f", {role}"
                                updated=True
                                break
                        if ( not updated ):
                            extracted_events.append({
                            "summary": f"Church Roster: {role}",
                            "start": start_dt,
                            "end": end_dt,
                            "description": f"Role: {role}"
                        })

    return extracted_events


def main():
    parser = argparse.ArgumentParser(description="Extract roster from pdf.")
    parser.add_argument("-i", "--input", required=True, help="Path to raw roster PDF file")
    parser.add_argument("-n", "--name", required=True, help="Target name to isolate")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: '{args.input}' not found.")
        return

    print(f"Analyzing structure of '{args.input}'...")
    extracted_shifts = parse_pdf_roster(args.input, args.name)

    if not extracted_shifts:
        print(f"No roster allocations found matching '{args.name}'.")
        return

    safe_filename = re.sub(r"[^\w\-_]", "_", args.name)
    output_ics = f"{safe_filename}.ics"

    c = Calendar()
    for shift in extracted_shifts:
        event = Event()
        event.name = shift["summary"]
        event.begin = shift["start"]
        event.end = shift["end"]
        event.description = shift["description"]
        c.events.add(event)
        print(f"Mapped: {event.name} on {shift['start'].strftime('%d/%m/%Y %I:%M %p')}")

    with open(output_ics, "w") as f:
        f.writelines(c.serialize_iter())

    print(f"\nSuccess! Found {len(extracted_shifts)} shifts. Saved to '{output_ics}'")


if __name__ == "__main__":
    main()
