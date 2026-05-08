import discord

from export import (
    export_csv,
    export_docx,
    export_pdf
)

# =========================
# EXPORT VIEW
# =========================
class ExportView(discord.ui.View):

    def __init__(self, report_data):

        super().__init__(timeout=300)

        self.report_data = report_data

    # =========================
    # CSV
    # =========================
    @discord.ui.button(
        label="CSV",
        style=discord.ButtonStyle.green
    )
    async def csv_btn(self, interaction, button):

        file = export_csv(self.report_data)

        await interaction.response.send_message(
            file=discord.File(file),
            ephemeral=True
        )

    # =========================
    # DOCX
    # =========================
    @discord.ui.button(
        label="DOCX",
        style=discord.ButtonStyle.gray
    )
    async def docx_btn(self, interaction, button):

        file = export_docx(self.report_data)

        await interaction.response.send_message(
            file=discord.File(file),
            ephemeral=True
        )

    # =========================
    # PDF
    # =========================
    @discord.ui.button(
        label="PDF",
        style=discord.ButtonStyle.red
    )
    async def pdf_btn(self, interaction, button):

        file = export_pdf(self.report_data)

        await interaction.response.send_message(
            file=discord.File(file),
            ephemeral=True
        )
