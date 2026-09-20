from dataclasses import dataclass
import os

@dataclass(frozen=True)
class Settings:
    kufar_profile_id: str = os.getenv('KUFAR_PROFILE_ID', '11093294')
    kufar_profile_url: str = os.getenv('KUFAR_PROFILE_URL', 'https://re.kufar.by/p/ooo-mezhdunarodnaya-rielterskaya-kompaniya-etazhi/11093294')
    bir_search_url: str = os.getenv('BIR_SEARCH_URL', 'https://bir.by/search-by-parameters/')
    bir_refresh_minutes: int = int(os.getenv('BIR_REFRESH_MINUTES', '15'))
    telegram_token: str = os.getenv('TELEGRAM_BOT_TOKEN', '')
    cf_account_id: str = os.getenv('CF_ACCOUNT_ID', '')
    cf_database_id: str = os.getenv('CF_D1_DATABASE_ID', '')
    cf_token: str = os.getenv('CF_D1_API_TOKEN', '')
    headless: bool = os.getenv('HEADLESS', '1') != '0'
    send_screenshots: bool = os.getenv('SEND_SCREENSHOTS', '1') != '0'

settings = Settings()
