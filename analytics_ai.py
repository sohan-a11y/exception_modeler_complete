"""
Analytics AI Module - V7.0
AI-powered analytics dashboard with visualizations
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from typing import Optional


def display_analytics_dashboard_ai(df: pd.DataFrame) -> None:
    """
    AI-powered analytics dashboard with intelligent insights.
    
    Provides:
    - Trend analysis for exception patterns
    - Confidence distribution analysis
    - Module-wise breakdown
    - Time-based pattern detection
    """
    if df.empty:
        st.info("📊 No data available for AI analytics. Process some exceptions first.")
        return
    
    st.subheader("🤖 AI-Powered Analytics")
    
    # Create metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total = len(df)
        st.metric("Total Exceptions", f"{total:,}")
    
    with col2:
        if 'Confidence_Score' in df.columns:
            avg_conf = df['Confidence_Score'].mean()
            st.metric("Avg Confidence", f"{avg_conf:.1f}%")
        else:
            st.metric("Avg Confidence", "N/A")
    
    with col3:
        if 'Resolution' in df.columns:
            purge_count = len(df[df['Resolution'] == 'PURGE'])
            st.metric("Auto-Purged", purge_count)
        else:
            st.metric("Auto-Purged", 0)
    
    with col4:
        if 'Resolution' in df.columns:
            investigate_count = len(df[df['Resolution'] == 'INVESTIGATE'])
            st.metric("Need Review", investigate_count)
        else:
            st.metric("Need Review", 0)
    
    st.markdown("---")
    
    # Charts row
    chart_col1, chart_col2 = st.columns(2)
    
    with chart_col1:
        st.markdown("#### 📈 Resolution Distribution")
        if 'Resolution' in df.columns:
            resolution_counts = df['Resolution'].value_counts()
            colors = ['#00cc96', '#ef553b', '#636efa', '#ffa15a', '#ab63fa']
            fig = go.Figure(data=[go.Pie(
                labels=resolution_counts.index,
                values=resolution_counts.values,
                hole=0.4,
                marker=dict(colors=colors[:len(resolution_counts)])
            )])
            fig.update_layout(height=350, margin=dict(t=20, b=20, l=20, r=20))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No resolution data available")
    
    with chart_col2:
        st.markdown("#### 🎯 Confidence Score Distribution")
        if 'Confidence_Score' in df.columns:
            fig = px.histogram(
                df, x='Confidence_Score', 
                nbins=20,
                color_discrete_sequence=['#636efa']
            )
            fig.update_layout(
                height=350,
                margin=dict(t=20, b=20, l=20, r=20),
                xaxis_title="Confidence Score (%)",
                yaxis_title="Count"
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No confidence data available")
    
    # Exception types breakdown
    if 'Exception_Type' in df.columns:
        st.markdown("#### 🔥 Top Exception Types")
        exc_counts = df['Exception_Type'].value_counts().head(10)
        fig = px.bar(
            x=exc_counts.values,
            y=exc_counts.index,
            orientation='h',
            color=exc_counts.values,
            color_continuous_scale='Blues'
        )
        fig.update_layout(
            height=400,
            margin=dict(t=20, b=20, l=20, r=20),
            xaxis_title="Count",
            yaxis_title="Exception Type",
            showlegend=False
        )
        fig.update_coloraxes(showscale=False)
        st.plotly_chart(fig, use_container_width=True)


def render_module_download_button(module_name: str, data: pd.DataFrame) -> None:
    """
    Render a download button for module-specific data export.
    
    Args:
        module_name: Name of the module for the export
        data: DataFrame containing the data to export
    """
    if data.empty:
        st.warning(f"No data available for {module_name}")
        return
    
    # Convert to CSV
    csv = data.to_csv(index=False)
    
    st.download_button(
        label=f"📥 Download {module_name} Data",
        data=csv,
        file_name=f"{module_name}_export.csv",
        mime="text/csv",
        use_container_width=True
    )


def generate_ai_insights(df: pd.DataFrame) -> list:
    """
    Generate AI-powered insights from exception data.
    
    Returns a list of insight strings based on pattern analysis.
    """
    insights = []
    
    if df.empty:
        return ["No data available for analysis"]
    
    # Analyze confidence distribution
    if 'Confidence_Score' in df.columns:
        avg_conf = df['Confidence_Score'].mean()
        if avg_conf >= 80:
            insights.append("✅ High overall confidence - most exceptions are well-understood")
        elif avg_conf >= 60:
            insights.append("⚠️ Moderate confidence - consider adding more KB patterns")
        else:
            insights.append("🔴 Low confidence - KB enhancement strongly recommended")
    
    # Analyze resolution distribution
    if 'Resolution' in df.columns:
        investigate_pct = len(df[df['Resolution'] == 'INVESTIGATE']) / len(df) * 100
        if investigate_pct > 30:
            insights.append(f"⚠️ {investigate_pct:.1f}% require manual investigation")
        
        purge_pct = len(df[df['Resolution'] == 'PURGE']) / len(df) * 100
        if purge_pct > 50:
            insights.append(f"✅ {purge_pct:.1f}% auto-classified for purge")
    
    # Analyze exception types
    if 'Exception_Type' in df.columns:
        top_type = df['Exception_Type'].mode().iloc[0] if not df['Exception_Type'].mode().empty else "Unknown"
        top_count = len(df[df['Exception_Type'] == top_type])
        if top_count > len(df) * 0.2:
            insights.append(f"🔍 '{top_type}' is the most common exception type ({top_count} occurrences)")
    
    return insights if insights else ["Analysis complete - no specific patterns detected"]
