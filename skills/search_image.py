import requests
import os
import random

def search_image(keyword, save_dir='D:/Projects/YukiV6/temp_images'):
    """
    搜索并下载一张与关键词相关的图片（目前使用随机动漫图片API，关键词仅用于命名）。
    :param keyword: 关键词，用于文件名标识
    :param save_dir: 保存目录，默认为D:/Projects/YukiV6/temp_images
    :return: 成功返回图片文件绝对路径，失败返回None
    """
    os.makedirs(save_dir, exist_ok=True)
    # 使用随机二次元图片API
    url = 'https://api.btstu.cn/sjbz/api.php?lx=dongman&format=json'
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        img_url = data.get('imgurl')
        if not img_url:
            return None
        ext = os.path.splitext(img_url.split('?')[0])[1] or '.jpg'
        filename = f'{keyword}_{random.randint(1000,9999)}{ext}'
        filepath = os.path.join(save_dir, filename)
        img_data = requests.get(img_url, headers=headers, timeout=10).content
        with open(filepath, 'wb') as f:
            f.write(img_data)
        return filepath
    except Exception as e:
        print(f'Error: {e}')
        return None

if __name__ == '__main__':
    import sys
    keyword = sys.argv[1] if len(sys.argv) > 1 else '二次元男头'
    path = search_image(keyword)
    print(path)