import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

class SheetManager:
    def __init__(self):
        # 从环境变量读取 JSON Key
        json_str = os.getenv("GCP_SA_KEY")
        sheet_name = os.getenv("SHEET_NAME", "Wyckoff_Stock_List")
        
        if not json_str:
            raise ValueError("❌ 未找到 GCP_SA_KEY 环境变量")

        # 解析 JSON
        creds_dict = json.loads(json_str)
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # 打开表格
        self.sheet = client.open(sheet_name).sheet1

    def get_all_stocks(self):
        """读取所有股票，返回字典格式"""
        # get_all_records 会自动把第一行作为 Key
        # 返回列表: [{'Code': 600519, 'BuyDate': '...', ...}, {...}]
        records = self.sheet.get_all_records()
        
        stocks = {}
        for row in records:
            code = str(row.get('Code', '')).strip()
            if code:
                # 补全默认值
                date = str(row.get('BuyDate', '')).strip() or datetime.now().strftime("%Y-%m-%d")
                qty = str(row.get('Qty', '')).strip() or "0"
                price = str(row.get('Price', '')).strip() or "0.0"
                
                stocks[code] = {'date': date, 'qty': qty, 'price': price}
        return stocks

    def add_or_update_stock(self, code, date=None, qty=None, price=None):
        """添加或更新股票"""
        code = str(code)
        date = date or datetime.now().strftime("%Y-%m-%d")
        qty = qty or 0
        price = price or 0.0
        
        # 1. 查找是否存在
        try:
            cell = self.sheet.find(code)
            # 如果存在，更新这一行 (Row index = cell.row)
            # 假设列顺序是: Code(1), BuyDate(2), Qty(3), Price(4)
            self.sheet.update_cell(cell.row, 2, date)
            self.sheet.update_cell(cell.row, 3, qty)
            self.sheet.update_cell(cell.row, 4, price)
            return "Updated"
        except gspread.exceptions.CellNotFound:
            # 如果不存在，追加一行
            self.sheet.append_row([code, date, qty, price])
            return "Added"

    def remove_stock(self, code):
        """删除股票"""
        try:
            cell = self.sheet.find(str(code))
            self.sheet.delete_rows(cell.row)
            return True
        except gspread.exceptions.CellNotFound:
            return False

    def clear_all(self):
        """清空（保留表头）"""
        # resize(1) 会把所有数据行删掉，只留第1行
        self.sheet.resize(rows=1) 
        self.sheet.resize(rows=100) # 再加回来一些空行
