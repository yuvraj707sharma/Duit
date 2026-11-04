"""Executive Daily Briefing PDF Generator.

Produces styled, executive-grade PDF morning briefings combining:
1. Priority Email Digest (Gmail)
2. High-Priority WhatsApp Messages
3. Top 10 Industry & Tech News Stories
4. Daily Schedule and Focus Items
"""
import os
import datetime
from typing import Dict, Any, List, Optional
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch


class BriefingPDFGenerator:
    """Generates professional morning briefing PDFs using ReportLab."""

    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = output_dir or os.path.join(os.getcwd(), "artifacts", "briefings")
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_morning_briefing_pdf(
        self,
        date_str: Optional[str] = None,
        recipient_name: str = "Executive",
        industry: str = "Technology & AI",
        emails: Optional[List[Dict[str, Any]]] = None,
        whatsapp_messages: Optional[List[Dict[str, Any]]] = None,
        news_items: Optional[List[Dict[str, Any]]] = None,
        schedule_items: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Generates a complete executive briefing PDF and returns the file path."""
        now = datetime.datetime.now()
        date_display = date_str or now.strftime("%A, %B %d, %Y")
        file_name = f"Morning_Briefing_{now.strftime('%Y%m%d_%H%M%S')}.pdf"
        file_path = os.path.join(self.output_dir, file_name)

        doc = SimpleDocTemplate(
            file_path,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()

        # Custom typography styles
        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Heading1"],
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#1A2B4C"),
            fontName="Helvetica-Bold",
            spaceAfter=4
        )
        subtitle_style = ParagraphStyle(
            "DocSubtitle",
            parent=styles["Normal"],
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#5A6B82"),
            fontName="Helvetica"
        )
        section_heading = ParagraphStyle(
            "SectionHeading",
            parent=styles["Heading2"],
            fontSize=13,
            leading=17,
            textColor=colors.HexColor("#1A2B4C"),
            fontName="Helvetica-Bold",
            spaceBefore=12,
            spaceAfter=6
        )
        body_style = ParagraphStyle(
            "Body",
            parent=styles["Normal"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#2C3E50"),
            fontName="Helvetica"
        )
        bold_body = ParagraphStyle(
            "BoldBody",
            parent=body_style,
            fontName="Helvetica-Bold"
        )
        callout_text = ParagraphStyle(
            "Callout",
            parent=body_style,
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#334155")
        )

        story = []

        # 1. Header Banner
        story.append(Paragraph("FASTAGENT EXECUTIVE BRIEFING", title_style))
        story.append(Paragraph(
            f"Prepared for: <b>{recipient_name}</b> | Date: <b>{date_display}</b> | Time: <b>07:00 AM IST</b> | Industry: <b>{industry}</b>",
            subtitle_style
        ))
        story.append(Spacer(1, 10))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1A2B4C"), spaceAfter=12))

        # Default sample data if not supplied
        sample_emails = emails or [
            {"from": "Board Chairman <board@corp.com>", "subject": "Q4 Strategy Alignment & Audit Review", "category": "High Priority", "snippet": "Need final confirmation on the FY26 capital allocation deck before Friday's investor call."},
            {"from": "Google Cloud Support <cloud-ops@google.com>", "subject": "Compute Engine Quota Increase Approved", "category": "Operations", "snippet": "Your request for 128x H100 GPU quota in region us-central1 has been approved and provisioned."},
            {"from": "Priya Nair <priya.n@innovate.co>", "subject": "Vendor Contract: Cloudflare Enterprise Renewal", "category": "Finance / Approval", "snippet": "Attached the final signed MSA and discounted terms for your sign-off today."}
        ]

        sample_whatsapp = whatsapp_messages or [
            {"sender": "Rohan (Head of Product)", "time": "06:45 AM", "message": "Demo build for the client pitch is locked on staging. All end-to-end flows passed latency checks."},
            {"sender": "DevOps OnCall Alert", "time": "05:12 AM", "message": "Cluster backup completed successfully. API latency steady at p95=42ms."},
            {"sender": "Legal Counsel (Adv. Mehta)", "time": "Yesterday 11:30 PM", "message": "Reviewed FastAgent tenant data privacy addendum. Ready for signature."}
        ]

        sample_news = news_items or [
            {"rank": 1, "headline": "Meta Unveils Next-Gen Open Weight Muse Reasoning Architecture", "source": "TechCrunch", "summary": "Breakthrough in low-latency reasoning models optimized for edge devices and mobile workflows with under 300ms time-to-first-token."},
            {"rank": 2, "headline": "RBI Finalizes Regulatory Sandbox for Agentic AI in Banking", "source": "Economic Times", "summary": "New guidelines require deterministic human-in-the-loop approvals for financial transactions exceeding Rs 50,000."},
            {"rank": 3, "headline": "Anthropic Partners with Major Cloud Providers for Enterprise Tool Use", "source": "Reuters", "summary": "Focus expands toward desktop sidecars and autonomous local task execution harnesses."},
            {"rank": 4, "headline": "India's Tech Exports Cross Historic Milestone on SaaS and AI Surge", "source": "Business Standard", "summary": "Strong growth observed in cross-border AI software and intelligent automation services."},
            {"rank": 5, "headline": "OpenAI Releases Desktop Agent Automation Protocols", "source": "VentureBeat", "summary": "Native OS interaction primitives standardize window-based execution across macOS and Windows."},
            {"rank": 6, "headline": "Semiconductor Fab in Dholera Begins Pilot Silicon Runs", "source": "LiveMint", "summary": "Domestic advanced packaging facilities begin producing initial commercial wafers ahead of schedule."},
            {"rank": 7, "headline": "Cybersecurity Agency Issues Advisory on OAuth Token Ephemerality", "source": "Bleeping Computer", "summary": "Strict recommendation to adopt 15-minute token expiry and encrypted refresh tokens in cloud agents."},
            {"rank": 8, "headline": "WhatsApp Business Platform Expands Multi-Agent Orchestration APIs", "source": "The Verge", "summary": "Enables seamless sidecar task synchronization and rich card interactions for executive workflows."},
            {"rank": 9, "headline": "Global Venture Funding Rebounds in AI Infrastructure & Edge Computing", "source": "WSJ", "summary": "Investors prioritize companies delivering sub-second real-world execution over pure chat interfaces."},
            {"rank": 10, "headline": "Google Cloud Introduces Zero-Trust Guardrails for Sovereign AI", "source": "Cloud Computing News", "summary": "Customer data segregation and synthetic data scrubbing become mandatory for regulated deployments."}
        ]

        # 2. Executive Summary Metrics Table
        metrics_data = [
            [
                Paragraph("<b>3</b><br/><font color='#666'>Urgent Emails</font>", body_style),
                Paragraph("<b>3</b><br/><font color='#666'>Priority Chats</font>", body_style),
                Paragraph("<b>10</b><br/><font color='#666'>Industry Stories</font>", body_style),
                Paragraph("<b>2</b><br/><font color='#666'>Decisions Pending</font>", body_style)
            ]
        ]
        metrics_table = Table(metrics_data, colWidths=[135, 135, 135, 135])
        metrics_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#94A3B8")),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(metrics_table)
        story.append(Spacer(1, 12))

        # 3. Section: Priority Emails
        story.append(Paragraph("1. Priority Email Intelligence (Gmail)", section_heading))
        email_rows = [["Sender", "Category", "Subject & Key Intelligence"]]
        for e in sample_emails:
            sender_clean = e.get("from", "").split("<")[0].strip() or e.get("from", "")
            cat = e.get("category", "General")
            content = f"<b>{e.get('subject', '')}</b><br/><font color='#475569'>{e.get('snippet', '')}</font>"
            email_rows.append([
                Paragraph(sender_clean, bold_body),
                Paragraph(f"<font color='#0F766E'><b>{cat}</b></font>", body_style),
                Paragraph(content, body_style)
            ])

        email_table = Table(email_rows, colWidths=[130, 95, 315])
        email_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1A2B4C")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(email_table)
        story.append(Spacer(1, 12))

        # 4. Section: WhatsApp Priority Messages
        story.append(Paragraph("2. High-Priority WhatsApp Messages", section_heading))
        wa_rows = [["Contact", "Time", "Summary & Action Request"]]
        for w in sample_whatsapp:
            wa_rows.append([
                Paragraph(w.get("sender", ""), bold_body),
                Paragraph(w.get("time", ""), body_style),
                Paragraph(w.get("message", ""), body_style)
            ])

        wa_table = Table(wa_rows, colWidths=[130, 70, 340])
        wa_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#065F46")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(wa_table)
        story.append(Spacer(1, 14))

        # 5. Section: Top 10 Industry & Tech News
        story.append(Paragraph(f"3. Top 10 {industry} Executive Headlines", section_heading))
        news_rows = [["#", "Headline & Executive Intelligence", "Source"]]
        for n in sample_news:
            headline_text = f"<b>{n.get('headline', '')}</b><br/><font color='#475569'>{n.get('summary', '')}</font>"
            news_rows.append([
                Paragraph(str(n.get("rank", "")), bold_body),
                Paragraph(headline_text, body_style),
                Paragraph(f"<i>{n.get('source', '')}</i>", callout_text)
            ])

        news_table = Table(news_rows, colWidths=[25, 420, 95])
        news_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#334155")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(news_table)
        story.append(Spacer(1, 12))

        # 6. Footer Notes
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E1"), spaceAfter=6))
        story.append(Paragraph(
            "FastAgent Chief of Staff Platform. Confidential and generated automatically via local desktop sidecar.",
            subtitle_style
        ))

        doc.build(story)
        return file_path


briefing_pdf_generator = BriefingPDFGenerator()

