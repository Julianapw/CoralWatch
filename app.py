import streamlit as st
from dashboard.ui import main

if __name__ == "__main__":
    st.set_page_config(layout='wide', page_title='CoralWatch', initial_sidebar_state='expanded')
    main()
