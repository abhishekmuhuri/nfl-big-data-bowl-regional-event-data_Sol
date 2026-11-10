# Route Relay

Route Relay is a planned Python dashboard for analyzing how NFL wide receivers, tight ends, and running backs create complementary separation windows during passing plays.
It will measure option coverage, the longest gap without a separated receiver, each receiver's unique contribution, window duration, and separation beyond the first-down line.
Coaches and analysts will be able to compare similar situations and inspect receiver timelines and animated plays to identify route-timing questions for film review and practice.
The planned analysis uses the [2021 Weeks 1-8 NFL tracking and PFF scouting dataset](https://github.com/ThompsonJamesBliss/nfl-big-data-bowl-regional-event-data), with pandas and NumPy for processing, Plotly for visualization, and Streamlit for the interface.
This repository currently contains the project setup, with implementation and findings pending; separation will be treated as a spatial proxy rather than proof of a safe throwing opportunity.
