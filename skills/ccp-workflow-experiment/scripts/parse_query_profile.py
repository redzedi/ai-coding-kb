#!/usr/bin/env python3
"""
scripts/parse_query_profile.py

A generalized Spark / Databricks Physical Plan and Query Profile Analyzer.
Parses query profile text files to identify physical table scans, shuffles, 
reused exchanges, and memory disk spills.
"""

import sys
import os
import re
from collections import defaultdict

def parse_query_profile(file_path):
    if not os.path.exists(file_path):
        print(f"Error: Profile file not found at {file_path}", file=sys.stderr)
        return False

    print(f"\n==================================================================")
    print(f" ANALYZING QUERY PROFILE: {os.path.basename(file_path)}")
    print(f"==================================================================")

    scans = defaultdict(list)
    reused_exchanges = []
    shuffles_count = 0
    spills = defaultdict(list)
    
    # 1. Regex to match physical scans (e.g. PhotonScan parquet table, Scan parquet table)
    scan_pattern = re.compile(
        r'(?:PhotonScan|Scan)\s+(?:parquet|delta|json|csv|orc)?\s*([a-zA-Z0-9_\-\.]+)(?:\s*\(\d+\))?', 
        re.IGNORECASE
    )
    
    # Fallback to catch standard table reads/scans
    fallback_scan_pattern = re.compile(
        r'\bscan\b.*\b(ams\.[a-zA-Z0-9_]+|[a-zA-Z0-9_\-\.]+\.[a-zA-Z0-9_\-\.]+)\b', 
        re.IGNORECASE
    )
    
    # 2. Regex for Reused Exchanges/Subqueries
    reused_pattern = re.compile(
        r'ReusedExchange\s*(?:\(\d+\))?|ReusedSubquery\s*(?:\(\d+\))?|Reused\s+Exchange', 
        re.IGNORECASE
    )
    
    # 3. Regex for Shuffles/Exchanges
    shuffle_pattern = re.compile(
        r'ShuffleExchange|ShuffleQueryStage|PhotonShuffleMapStage|PhotonShuffleExchange|Exchange', 
        re.IGNORECASE
    )
    
    # 4. Regex for Disk Spills & Memory Pressure
    spill_pattern = re.compile(
        r'spill|spilled|memory pressure|disk spill|bytes spilled', 
        re.IGNORECASE
    )

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                clean_line = line.strip()
                if not clean_line:
                    continue

                # Detect physical scans
                scan_match = scan_pattern.search(clean_line)
                if scan_match:
                    table_name = scan_match.group(1)
                    scans[table_name].append((line_num, clean_line))
                else:
                    fb_match = fallback_scan_pattern.search(clean_line)
                    if fb_match:
                        table_name = fb_match.group(1)
                        scans[table_name].append((line_num, clean_line))

                # Detect Reused Exchanges
                if reused_pattern.search(clean_line):
                    reused_exchanges.append((line_num, clean_line))

                # Count Shuffles
                if shuffle_pattern.search(clean_line):
                    shuffles_count += 1

                # Detect Spills or Memory Pressure
                if spill_pattern.search(clean_line):
                    if any(kw in clean_line.lower() for kw in ["bytes", "spill", "pressure", "swap", "accumulate", "size"]):
                        spills[clean_line].append(line_num)

    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        return False

    # --- REPORTING ---
    print(f"\n[1] PHYSICAL SCANS SUMMARY:")
    print(f"------------------------------------------------------------------")
    if not scans:
        print("✅ No physical table scans detected in the profile text.")
    else:
        total_physical_scans = 0
        redundant_tables_count = 0
        
        for table, occurrences in sorted(scans.items(), key=lambda x: len(x[1]), reverse=True):
            count = len(occurrences)
            total_physical_scans += count
            if count > 1:
                status = "⚠️ REDUNDANT SCANS DETECTED!"
                redundant_tables_count += 1
            else:
                status = "✅ OPTIMAL (Single Scan)"
            
            print(f"Table: {table}")
            print(f"  - Count: {count} scan(s) ({status})")
            print(f"  - Plan Line(s): {', '.join(str(o[0]) for o in occurrences)}")
            
        print(f"\nTotal Physical Scans Across All Tables: {total_physical_scans}")
        print(f"Redundant Scan Tables: {redundant_tables_count}")

    print(f"\n[2] OPTIMIZATION & SHUFFLE TELEMETRY:")
    print(f"------------------------------------------------------------------")
    print(f"Total Shuffle / Exchange Nodes in Plan: {shuffles_count}")
    print(f"Reused Exchanges Detected: {len(reused_exchanges)} (Catalyst-reused shuffles)")
    for line_num, details in reused_exchanges[:10]:
        print(f"  - Line {line_num}: {details}")
    if len(reused_exchanges) > 10:
        print(f"  - ... and {len(reused_exchanges) - 10} more reused exchange nodes.")

    print(f"\n[3] INFRASTRUCTURE / MEMORY PRESSURE & SPILLS:")
    print(f"------------------------------------------------------------------")
    if not spills:
        print("✅ No explicit disk spills or memory pressure warnings detected.")
    else:
        print(f"⚠️ Detected {sum(len(lines) for lines in spills.values())} occurrences of disk spill/memory pressure:")
        for detail, lines in sorted(spills.items(), key=lambda x: len(x[1]), reverse=True)[:10]:
            print(f"  - Occurred {len(lines)} times on line(s): {', '.join(map(str, lines))}")
            print(f"    Detail: {detail}")
        if len(spills) > 10:
            print(f"  - ... and {len(spills) - 10} other unique spill indicators.")

    print(f"\n==================================================================")
    print(f" END OF PROFILE REPORT")
    print(f"==================================================================\n")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 parse_query_profile.py <profile_file_path>")
        sys.exit(1)
    
    parse_query_profile(sys.argv[1])
