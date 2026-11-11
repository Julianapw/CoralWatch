import streamlit as st
from dashboard.ui import main

if __name__ == "__main__":
    st.set_page_config(layout='wide', page_title='CoralWatch', page_icon='🪸', initial_sidebar_state='expanded')
    main()
