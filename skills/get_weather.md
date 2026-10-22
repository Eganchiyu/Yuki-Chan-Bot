# get_weather：查询指定城市和日期的天气信息

## 功能
使用 wttr.in 免费API获取天气数据，支持指定日期（预报）或当前天气。

## 参数
- `city` (str): 城市名称，支持中文，如 "西安"
- `date` (str, optional): 日期，格式 "YYYY-MM-DD"。不提供则返回当前天气。

## 返回
- str: 天气描述，包含天气状况、温度、风速、风向等。

## 示例
```python
print(get_weather("西安", "2026-06-05"))
# 输出：西安2026-06-05天气：Sunny，最高温度37°C，最低温度21°C，风速6km/h，风向ENE

print(get_weather("北京"))
# 输出：北京当前天气：Partly cloudy，温度22°C，风速10km/h，风向N，湿度45%
```

## 依赖
- requests

## 备注
- 网络需要能访问 wttr.in
- 日期为未来3天内的预报，更早的日期可能无数据