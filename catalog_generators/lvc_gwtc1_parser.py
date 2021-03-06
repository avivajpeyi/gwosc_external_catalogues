import glob
import os

import h5py
import pandas as pd
from bilby.gw.conversion import (
    luminosity_distance_to_redshift
)
from tqdm import tqdm

from . import utils
from .catalog_generator import CatalogGenerator
from .event_keys import GWOSC_KEYS, REQUIRED_PARAMETERS
from .event_parser import EventParser
from .utils import dict_to_json, summarise_samples

DATA_DIR = "../data/lvc_search/gwtc1"

SEARCH_PARAMS = {
    "luminosity_distance_Mpc": "luminosity distance [Mpc]",
    "m1_detector_frame_Msun": "primary (larger) black hole mass (detector frame) [solar mass]",
    "m2_detector_frame_Msun": "secondary (smaller) black hole mass (detector frame) [solar mass]",
    "right_ascension": "right ascension of source  [rad].",
    "declination": "declination of the source [rad]",
    "costheta_jn": "cosine of the angle between line of sight and total angular momentum vector of system.",
    "spin1": "primary (larger) black hole spin magnitude (dimensionless)",
    "costilt1": "cosine of the zenith angle between the spin and the orbital angular momentum vector of system.",
    "spin2": "secondary (smaller) black hole spin magnitude (dimensionless)",
    "costilt2": "cosine of the zenith angle between the spin and the orbital angular momentum vector of system."
}


def main():
    generate_lvc_catalog(data_dir=DATA_DIR,
                         out_catalog_fname="../data/lvc_catalog_new.json")


def generate_lvc_catalog(data_dir, out_catalog_fname):
    event_samples = load_event_samples_to_dataframes(data_dir)
    event_samples = make_events_gwosc_compatible(event_samples)
    event_summary = summarise_all_events(event_samples)
    dict_to_json(
        json_fname=out_catalog_fname,
        data_dict=dict(events=event_summary)
    )
    print("Completed catalog generation.")


def summarise_all_events(events_samples_dict):
    summary_dict = {}
    for event_name, event_df in events_samples_dict.items():
        event_summary_dict = summarise_event_df(event_df)
        event_summary_dict['commonName'] = event_name
        summary_dict[event_name] = event_summary_dict
    return summary_dict


def load_event_samples_to_dataframes(data_dir):
    """Load LVS posterior files into dict of df"""
    events_samples_dict = {}
    files = glob.glob(os.path.join(data_dir, "*.h*5"))
    for file in tqdm(files, desc="Reading LVC Posteriors", total=len(files)):
        event_name = os.path.basename(file).split(".h")[0]
        event_name = event_name.split("_")[0]
        event_hdf = h5py.File(file, mode='r')
        event_dict = {k: event_hdf[f"Overall_posterior"][k][()] for k in
                      SEARCH_PARAMS.keys()}
        event_df = pd.DataFrame(event_dict)
        events_samples_dict[event_name] = event_df
    return events_samples_dict


def make_events_gwosc_compatible(events_df_container):
    for event_name in events_df_container.keys():
        events_df_container[event_name] = convert_df_to_gwosc_df(
            events_df_container[event_name])
    return events_df_container


def convert_df_to_gwosc_df(df: pd.DataFrame) -> pd.DataFrame:
    converted_df = df.copy()
    # rename
    converted_df['mass_1'] = converted_df['m1_detector_frame_Msun']
    converted_df['mass_2'] = converted_df['m2_detector_frame_Msun']
    converted_df['mass_ratio'] = converted_df['mass_2'] / converted_df['mass_1']
    converted_df['ra'] = converted_df['right_ascension']
    converted_df['dec'] = converted_df['declination']
    return converted_df


def summarise_event_df(event_df):
    summary = {}
    for param in event_df.columns:
        summary[f"{param}_lower"], summary[f"{param}_upper"], summary[param] = \
            summarise_samples(event_df[param])

    for param_type in ["_lower", "_upper", ""]:
        summary[f'redshift{param_type}'] = \
            float(luminosity_distance_to_redshift(
                summary[f'luminosity_distance{param_type}']))
        for key in ['mass_1', 'mass_2', 'chirp_mass', 'total_mass']:
            summary[f'{key}_source{param_type}'] = \
                summary[f"{key}{param_type}"] / (1 + summary[f'redshift{param_type}'])

    summary = {k: summary.get(k, None) for k in GWOSC_KEYS}
    summary['version'] = 1
    # summary['reference'] = "https://github.com/jroulet/O2_samples/"
    # summary['catalog.shortName'] = "IAS"
    return summary


class LvcGwtc1Catalog(CatalogGenerator):
    pass


from typing import List


class LvcGwtc1EventParser(EventParser):

    @staticmethod
    def get_search_parameters() -> List[str]:
        return list(SEARCH_PARAMS.keys())

    @classmethod
    def load_event_samples(cls, sample_filename: str) -> EventParser:
        event_hdf = h5py.File(sample_filename, mode='r')
        event_dict = {k: event_hdf[f"Overall_posterior"][k][()] for k in
                      LvcGwtc1EventParser.get_search_parameters()}
        return cls(
            samples=pd.DataFrame(event_dict),
            datasource=sample_filename,
            catalog="LVC-GWTC1",
        )

    @staticmethod
    @utils.sort_parameters
    def standardise_samples(samples: pd.DataFrame) -> pd.DataFrame:
        samples['luminosity_distance'] = samples["luminosity_distance_Mpc"]
        samples['redshift'] = utils.get_redshift_from_dl(samples['luminosity_distance'])
        for ii in [1, 2]:
            samples[f"mass_{ii}_source"] = samples[f"m{ii}_detector_frame_Msun"] / (
                    1 + samples["redshift"]
            )
            samples[f"a_{ii}"] = samples[f"spin{ii}"]
            samples[f"cos_tilt_{ii}"] = samples[f"costilt{ii}"]
            # tilt = arccos(s1z / s1Mag)
            samples[f'spin_{ii}z'] = samples[f"costilt{ii}"]
        samples["mass_ratio"] = samples["mass_2_source"] / samples["mass_1_source"]
        samples['ra'] = samples['right_ascension']
        samples['dec'] = samples['declination']

        samples = utils.add_aligned_component_spins(samples)
        samples['incl'] = 0
        samples['phi_12'] = 0
        samples['phi_jl'] = 0
        samples['geocent_time'] = 0
        return samples


if __name__ == "__main__":
    main()
