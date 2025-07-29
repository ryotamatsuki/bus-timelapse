# Ehime Bus Time‑Lapse Theater

This repository contains a prototype implementation of the **Ehime Bus Time‑Lapse Theater**.  
The goal of the project is to visualise the movement of bus services operated in the Ehime region of Japan using open public transport data (GTFS).  
It provides a Streamlit application that allows a user to select a day and watch the buses move across the region in a 3‑dimensional deck.gl map.  
Under the hood the app converts static GTFS timetable information into per‑trip position traces sampled every five seconds.

## Features

* **Data preprocessing** – A `path_builder` module reads the GTFS files and constructs a `bus_trails_<YYYY‑MM‑DD>.feather` cache in `data/cache/`.  For each trip the module interpolates the location of the bus every five seconds between consecutive stops.  
* **Service filtering** – A `service_filter` module exposes a helper to find valid `service_id` values for a given date by reading `calendar.txt` and `calendar_dates.txt` and to convert `HH:MM:SS` times (even beyond 24:00) into seconds.  
* **Streamlit app** – `app.py` defines a Streamlit UI with a sidebar for picking the date, playback speed and map theme.  After a cache is built the user can watch an animated 3D visualisation of bus movements using a `TripsLayer` from Pydeck.  
* **GitHub Actions workflow** – A sample workflow in `.github/workflows/gtfs_preprocess.yml` demonstrates how to schedule nightly downloads of new GTFS feeds and build caches for the following day.

## Directory structure

```
bus‑timelapse‑theater/
├── .github/workflows/gtfs_preprocess.yml   # Example CI workflow
├── app.py                                  # Streamlit front end
├── data/
│   ├── cache/                              # Generated Feather caches
│   └── gtfs/
│       ├── 2025‑07‑03/                     # Example GTFS feed (unpacked)
│       └── LATEST -> 2025‑07‑03            # Symlink to the most recent feed
├── modules/
│   ├── path_builder.py                     # 5‑second interpolation logic
│   ├── service_filter.py                   # Service filtering and time utils
│   └── gemini_helper.py                    # Placeholder for narration generation
├── scripts/
│   └── download_gtfs.py                    # Script to download and hash feeds
├── tests/
│   └── test_path_builder.py                # Simple unit test example
├── .gitignore
├── .pre‑commit‑config.yaml
├── README.md
└── requirements.txt
```

## Installation

1. Create a Python 3.11 environment (for example using `python -m venv .venv` and `source .venv/bin/activate`).
2. Install the dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Unpack a GTFS zip into `data/gtfs/<YYYY‑MM‑DD>/` and update the `LATEST` symlink accordingly.  An example feed (`AllLines‑20250703.zip`) has already been extracted into `data/gtfs/2025‑07‑03` in this repository.

## Usage

To generate a cache file for a given day run the following command:

```bash
python -m modules.path_builder --date 2025‑07‑10
```

This creates `data/cache/bus_trails_2025‑07‑10.feather` containing latitude, longitude and timestamp columns for every trip.  When you first start the Streamlit app it will automatically build the cache for the selected date if it does not already exist.

To launch the Streamlit app locally run:

```bash
streamlit run app.py
```

Then open the displayed URL in your browser.  Use the sidebar controls to choose a date, select a playback speed and change between light and dark map themes.  The application will display an animated 3D map of buses moving around Ehime.

## Limitations

* The path builder uses straight–line interpolation between stops because the provided dataset does not include detailed shape geometry.  If shape data becomes available it can be incorporated by replacing the interpolation logic in `modules/path_builder.py`.
* This repository does not perform any deployment; the GitHub Actions workflow is provided as an example only.
* Narration using Gemini and MP4 export are not implemented in this prototype.  A placeholder helper function is provided in `modules/gemini_helper.py`.

## License

This project is licensed under the MIT License.
