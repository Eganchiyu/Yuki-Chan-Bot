import requests
import json

def get_weather(city, date=None):
    """
    使用 wttr.in 获取指定城市和日期的天气信息。
    参数：
        city (str): 城市名称，如 "西安"
        date (str, optional): 日期，格式 "YYYY-MM-DD"。如果为 None，则返回当前天气。
    返回：
        str: 天气描述字符串
    """
    url = f"https://wttr.in/{city}?format=j1&lang=zh"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if date:
                weather = data.get('weather', [])
                for day in weather:
                    if day.get('date') == date:
                        maxtemp = day.get('maxtempC', 'N/A')
                        mintemp = day.get('mintempC', 'N/A')
                        hourly = day.get('hourly', [])
                        if hourly:
                            mid = hourly[len(hourly)//2]
                            weather_desc = mid.get('weatherDesc', [{}])[0].get('value', 'N/A')
                            wind_speed = mid.get('windspeedKmph', 'N/A')
                            wind_dir = mid.get('winddir16Point', 'N/A')
                        else:
                            weather_desc = 'N/A'
                            wind_speed = 'N/A'
                            wind_dir = 'N/A'
                        return f"{city}{date}天气：{weather_desc}，最高温度{maxtemp}°C，最低温度{mintemp}°C，风速{wind_speed}km/h，风向{wind_dir}"
                return f"未找到{date}的预报数据"
            else:
                current = data.get('current_condition', [{}])[0]
                temp = current.get('temp_C', 'N/A')
                weather_desc = current.get('weatherDesc', [{}])[0].get('value', 'N/A')
                wind_speed = current.get('windspeedKmph', 'N/A')
                wind_dir = current.get('winddir16Point', 'N/A')
                humidity = current.get('humidity', 'N/A')
                return f"{city}当前天气：{weather_desc}，温度{temp}°C，风速{wind_speed}km/h，风向{wind_dir}，湿度{humidity}%"
        else:
            return f"请求失败，状态码：{response.status_code}"
    except Exception as e:
        return f"请求异常：{e}"

if __name__ == "__main__":
    # 测试
    print(get_weather("西安", "2026-06-05"))
    print(get_weather("北京"))