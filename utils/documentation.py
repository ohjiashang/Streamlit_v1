import pandas as pd
import numpy as np
import os
from datetime import datetime
import matplotlib.pyplot as plt
import streamlit as st
import urllib.parse


def display_doc(folder, filename):
    encoded_filename = urllib.parse.quote(filename)
    url = f"https://firebasestorage.googleapis.com/v0/b/hotei-streamlit.firebasestorage.app/o/{folder}%2F{encoded_filename}?alt=media"
    st.markdown(
        f"""
        <div style="padding: 0;">
            <iframe 
                src="{url}" 
                width="100%" 
                height="800" 
                style="border: none; margin: 0; padding: 0;"
            ></iframe>
        </div>
        """,
        unsafe_allow_html=True
    )