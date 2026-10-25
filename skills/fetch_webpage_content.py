import requests
from bs4 import BeautifulSoup
import sys

def fetch_content(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'html.parser')
        # 提取正文段落
        paragraphs = soup.find_all('p')
        text = '\n'.join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
        return text[:2000]  # 限制长度
    except Exception as e:
        return f'获取失败: {str(e)}'

if __name__ == '__main__':
    url = 'http://www.baidu.com/link?url=-w3l5spdA2B0XRFJseiS9CXfWx1ElQDLnXiRRHrb4DMbgHfuO0_xchvg0bwf46f3'
    print(fetch_content(url))