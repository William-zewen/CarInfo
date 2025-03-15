import asyncio
from playwright.async_api import async_playwright
import json
import random
import time
import os
import datetime
from typing import Dict, Any, Optional

class CarSpider:
    def __init__(self, url, name=None, car_name=None, output_dir=None):
        self.url = url
        self.name = name if name else '未知品牌'
        self.car_name = car_name if car_name else '未知车型'
        # 如果没有指定输出目录，则使用默认的日期时间格式目录
        if output_dir is None:
            # 创建以当前日期时间（精确到分钟）命名的文件夹
            self.output_dir = datetime.datetime.now().strftime('%Y%m%d%H%M')
            # 确保目录存在
            if not os.path.exists(self.output_dir):
                os.makedirs(self.output_dir)
                print(f'已创建输出目录: {self.output_dir}')
        else:
            self.output_dir = output_dir
            if not os.path.exists(self.output_dir):
                os.makedirs(self.output_dir)
                print(f'已创建指定的输出目录: {self.output_dir}')
        
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0'
        ]

    async def init_browser(self):
        """初始化浏览器"""
        self.playwright = await async_playwright().start()
        # 使用chromium，开启无头模式
        self.browser = await self.playwright.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--disable-gpu',
                '--window-size=1920,1080'
            ]
        )

    async def create_context(self):
        """创建浏览器上下文"""
        return await self.browser.new_context(
            user_agent=random.choice(self.user_agents),
            viewport={'width': 1920, 'height': 1080},
            device_scale_factor=1,
            java_script_enabled=True,
            bypass_csp=True,
            ignore_https_errors=True
        )

    async def wait_for_page_load(self, page):
        """等待页面加载完成"""
        try:
            # 等待页面加载完成
            await page.wait_for_load_state('domcontentloaded', timeout=60000)
            await page.wait_for_load_state('networkidle', timeout=60000)
            
            # 等待主要内容容器加载
            try:
                # 尝试多个可能的选择器
                selectors = [
                    'div.table-box.main-table-box',
                    '.car-config',
                    '.parameter-list',
                    '.config-list',
                    '.spec-list'
                ]
                
                for selector in selectors:
                    try:
                        await page.wait_for_selector(selector, state='visible', timeout=30000)
                        print(f'找到内容容器，使用选择器: {selector}')
                        return True
                    except Exception:
                        continue
                        
                print('所有选择器都未找到匹配内容')
                return False
                
            except Exception as e:
                print(f'等待内容加载失败: {str(e)}')
                return False
            
            # 注入JavaScript绕过检测
            await page.evaluate("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            
            return True
        except Exception as e:
            print(f'页面加载过程发生错误: {str(e)}')
            return False

    async def extract_car_info(self, page) -> Optional[Dict[str, Any]]:
        """提取车辆信息"""
        try:
            # 等待页面加载完成
            await page.wait_for_load_state('domcontentloaded', timeout=60000)
            await page.wait_for_load_state('networkidle', timeout=60000)
            
            # 获取所有车型信息
            car_styles = await page.query_selector_all('span.car-style-info')
            if not car_styles:
                print('尝试备选选择器获取车型信息...')
                car_styles = await page.query_selector_all('.car-name, .car-type, .config-header .item, .param-header .item')
                if not car_styles:
                    print('未找到车型信息')
                    return None
                
            print(f'找到 {len(car_styles)} 个车型')
            
            # 创建存储所有车型数据的字典
            all_car_data = {}
            
            # 先获取所有车型名称
            car_names = []
            for idx, car_style in enumerate(car_styles, 1):
                try:
                    car_name = await car_style.text_content()
                    car_name = car_name.strip()
                    if not car_name:
                        car_name = f'车型_{idx}'
                    car_names.append(car_name)
                    all_car_data[car_name] = {}
                    print(f'车型{idx}: {car_name}')
                except Exception as e:
                    print(f'获取车型名称时出错: {str(e)}')
                    car_names.append(f'车型_{idx}')
                    all_car_data[f'车型_{idx}'] = {}
            
            # 获取参数行
            param_rows = await page.query_selector_all('div.table-box.main-table-box tr.data-tr')
            if not param_rows:
                print('使用备选选择器尝试获取参数行...')
                param_rows = await page.query_selector_all('.parameter-list tr, .config-list tr, .spec-list tr')
                if not param_rows:
                    print('未找到参数行')
                    return None
            
            print(f'找到 {len(param_rows)} 个参数行')
            
            # 处理每个参数行
            for row in param_rows:
                try:
                    # 获取参数名
                    name_cell = await row.query_selector('td.name, td:first-child, .param-name, .label')
                    if not name_cell:
                        continue
                        
                    param_name = await name_cell.text_content()
                    param_name = param_name.strip()
                    
                    # 获取该行中所有的参数值单元格
                    value_cells = await row.query_selector_all('td.text, td:not(:first-child), .param-value, .value')
                    
                    # 确保找到的值单元格数量与车型数量一致
                    if len(value_cells) == len(car_names):
                        # 将每个值与对应的车型匹配
                        for i, (car_name, value_cell) in enumerate(zip(car_names, value_cells)):
                            try:
                                param_value = await value_cell.text_content()
                                param_value = param_value.strip()
                                
                                # 验证参数值
                                if param_name and param_value and param_value not in ['——', '/', '空', 'N/A']:
                                    all_car_data[car_name][param_name] = param_value
                                    print(f'提取参数: {car_name} - {param_name} = {param_value}')
                                else:
                                    print(f'跳过无效参数: {car_name} - {param_name} = {param_value}')
                            except Exception as e:
                                print(f'处理参数值时出错: {str(e)}')
                    else:
                        print(f'警告: 参数行 "{param_name}" 的值单元格数量({len(value_cells)})与车型数量({len(car_names)})不匹配')
                        # 尝试尽可能匹配
                        for i, value_cell in enumerate(value_cells):
                            if i < len(car_names):
                                try:
                                    car_name = car_names[i]
                                    param_value = await value_cell.text_content()
                                    param_value = param_value.strip()
                                    
                                    if param_name and param_value and param_value not in ['——', '/', '空', 'N/A']:
                                        all_car_data[car_name][param_name] = param_value
                                        print(f'提取参数(不完全匹配): {car_name} - {param_name} = {param_value}')
                                except Exception as e:
                                    print(f'处理不匹配参数值时出错: {str(e)}')
                except Exception as row_error:
                    print(f'处理参数行时出错: {str(row_error)}')
                    continue
            
            if not all_car_data:
                print('未提取到任何数据')
                return None
                
            print(f'成功提取数据，共 {len(all_car_data)} 个车型')
            return all_car_data
            
        except Exception as e:
            print(f'Error occurred during execution: {str(e)}')
            return None

    async def save_data(self, data: Dict[str, Any]):
        """保存数据到JSON文件"""
        try:
            # 生成文件名，包含车型名称
            filename = f'{self.name}_{self.car_name}.json'
            # 构建完整的文件路径，保存到指定的输出目录
            file_path = os.path.join(self.output_dir, filename)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            print(f'数据已成功保存到{file_path}文件')
            return data
        except Exception as e:
            print(f'保存数据时发生错误: {str(e)}')
            return None

    async def run(self):
        """运行爬虫"""
        try:
            await self.init_browser()
            context = await self.create_context()
            page = await context.new_page()
            
            max_retries = 3
            retry_count = 0
            result_data = None
            
            while retry_count < max_retries:
                try:
                    # 访问目标页面
                    print(f'正在访问: {self.url}')
                    await page.goto(self.url, wait_until='networkidle', timeout=30000)
                    
                    # 等待页面加载完成
                    if not await self.wait_for_page_load(page):
                        print(f'页面加载失败，正在进行第{retry_count + 1}次重试...')
                        retry_count += 1
                        continue
                    
                    # 提取车辆信息
                    car_info = await self.extract_car_info(page)
                    
                    if car_info:
                        # 保存数据到JSON文件
                        result_data = await self.save_data(car_info)
                        break
                    else:
                        print(f'提取数据失败，正在进行第{retry_count + 1}次重试...')
                        retry_count += 1
                        await asyncio.sleep(random.uniform(5, 10))
                        
                except Exception as e:
                    print(f'运行过程中发生错误: {str(e)}')
                    retry_count += 1
                    await asyncio.sleep(random.uniform(5, 10))
            
            if retry_count >= max_retries:
                print(f'车型 {self.car_name} 达到最大重试次数，跳过')
            
            return result_data
                
        except Exception as e:
            print(f'执行过程中发生错误: {str(e)}')
            return None
        finally:
            await self.browser.close()
            await self.playwright.stop()

async def process_car(car_info, output_dir):
    """处理单个车型"""
    try:
        name = car_info.get('name', '未知品牌')
        subname = car_info.get('subname', '未知车型')
        url = car_info.get('url')
        if not url:
            print(f'错误：车型 {subname} 缺少URL')
            return None
            
        print(f'\n开始处理, 品牌： {name}, 车型: {subname}, URL: {url}')
        spider = CarSpider(url, name, subname, output_dir)
        return await spider.run()
    except Exception as e:
        print(f'处理车型 {car_info.get("subname", "未知车型")} 时出错: {str(e)}')
        return None

async def process_all_cars():
    """处理所有车型"""
    try:
        # 创建以当前日期时间（精确到分钟）命名的文件夹
        output_dir = datetime.datetime.now().strftime('%Y%m%d%H%M')
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            print(f'已创建输出目录: {output_dir}')
        
        # 读取车型列表
        with open('car_list.json', 'r', encoding='utf-8') as f:
            car_list = json.load(f)
        
        if not car_list:
            print('错误：车型列表为空')
            return
            
        print(f'读取到 {len(car_list)} 个车型')
        
        # 存储所有车型的数据，使用两级结构：第一级是品牌名称，第二级是车型信息
        all_cars_data = {}
        
        # 依次处理每个车型
        for car_info in car_list:
            car_data = await process_car(car_info, output_dir)
            if car_data:
                brand_name = car_info.get('name', '未知品牌')
                subname = car_info.get('subname', '未知车型')
                
                # 如果品牌不存在，则创建
                if brand_name not in all_cars_data:
                    all_cars_data[brand_name] = {}
                
                # 将车型数据添加到对应品牌下
                all_cars_data[brand_name][subname] = car_data
        
        # 保存所有车型的数据到一个总的JSON文件
        all_cars_file_path = os.path.join(output_dir, 'all_cars_info.json')
        with open(all_cars_file_path, 'w', encoding='utf-8') as f:
            json.dump(all_cars_data, f, ensure_ascii=False, indent=4)
        print(f'所有车型数据已合并保存到{all_cars_file_path}文件')
            
    except Exception as e:
        print(f'处理车型列表时出错: {str(e)}')

def main():
    """主函数"""
    asyncio.run(process_all_cars())

if __name__ == '__main__':
    main()