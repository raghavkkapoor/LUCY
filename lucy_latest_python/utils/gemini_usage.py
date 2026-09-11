import re

def get_gemini_usage(page) -> dict:
    result = {'daily_usage_remaining': None, 'weekly_usage_remaining': None}
    page.reload(wait_until='domcontentloaded', timeout=30000)
    daily_usage_dom_text = page.locator('[data-test-id="gxu-currently"]').inner_text().lower()
    segment1 = daily_usage_dom_text.split('\n')[2]
    daily_usage = ''.join([char for char in segment1 if char.isdigit()])
    weekly_usage_dom_text = page.locator('[data-test-id="gxu-weekly"]').inner_text().lower()
    segment2 = weekly_usage_dom_text.split('\n')[4]
    weekly_usage = ''.join([char for char in segment2 if char.isdigit()])
    result['daily_usage_remaining'] = daily_usage
    result['weekly_usage_remaining'] = weekly_usage
    return result