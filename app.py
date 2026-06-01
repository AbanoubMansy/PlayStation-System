import os
import sys
import time
import sqlite3
import subprocess
from threading import Thread
from flask import Flask, jsonify, render_template_string, request
import webview
import subprocess

# دالة لجلب الرقم التسلسلي للمذربورد (بصمة الجهاز الفريدة)
def get_hardware_id():
    try:
        # أمر ويندوز داخلي لجلب سيريال المذربورد
        output = subprocess.check_output('wmic baseboard get serialnumber', shell=True)
        # تنظيف النص الناتج من الفراغات والأحرف الزائدة
        hw_id = output.decode().split('\n')[1].strip()
        return hw_id
    except Exception:
        # حل بديل لو الويندوز فيه مشكلة في الصلاحيات
        return "UNKNOWN_DEVICE_BOBOS"

# 🔐 قائمة الأجهزة المصرح لها بتشغيل السيستم (هنا بتحط سيريال جهاز العميل)
ALLOWED_DEVICES = [
    "إدخال_سيريال_جهاز_العميل_هنا", 
    "YOUR_OWN_PC_SERIAL_FOR_TESTING" # حط سيريال جهازك هنا عشان تعرف تجربه وتطوره
]

def check_license():
    current_hw_id = get_hardware_id()
    
    # إذا كان الجهاز مش في القائمة المسموح ليها، البرنامج يقفل فوراً
    if current_hw_id not in ALLOWED_DEVICES:
        # إظهار رسالة تنبيه للعميل قبل القفل
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw() # إخفاء نافذة التيكنتر الأساسية
        
        # رسالة احترافية تظهر للمشتري غير المصرح له
        messagebox.showerror(
            "خطأ في الترخيص ❌", 
            f"عذراً، هذه النسخة غير مرخصة للعمل على هذا الجهاز.\n\n"
            f"بصمة جهازك هي: {current_hw_id}\n"
            f"يرجى التواصل مع المطور (بيبو) لتفعيل النسخة."
        )
        sys.exit()

app = Flask(__name__)
DB_NAME = "bobos_ps.db"

# 🔑 يمكنك تغيير باسورد الأدمن من هنا
ADMIN_PASSWORD = "1234"

# =====================================================================
# 1. إعداد قاعدة البيانات (SQLite3)
# =====================================================================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # جدول الأجهزة
    cursor.execute('''CREATE TABLE IF NOT EXISTS devices (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE,
                        single_price REAL,
                        multi_price REAL,
                        status TEXT DEFAULT 'Available',
                        start_time REAL DEFAULT NULL,
                        mode TEXT DEFAULT 'single')''')
                        
    # جدول المشاريب والوجبات
    cursor.execute('''CREATE TABLE IF NOT EXISTS drinks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE,
                        price REAL)''')
                        
    # جدول طلبات الأجهزة النشطة حالياً
    cursor.execute('''CREATE TABLE IF NOT EXISTS active_orders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        device_name TEXT,
                        drink_name TEXT,
                        quantity INTEGER)''')
    
    # ضخ بيانات افتراضية لو قاعدة البيانات لسه جديدة عند أول تشغيل
    try:
        cursor.execute("INSERT INTO drinks (name, price) VALUES ('Pepsi', 15), ('Tea', 10), ('Coffee', 20)")
        cursor.execute("INSERT INTO devices (name, single_price, multi_price) VALUES ('Device 1 (PS5)', 40, 60), ('Device 2 (PS4)', 25, 35), ('Device 3 (VIP)', 50, 80)")
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

# =====================================================================
# 2. واجهة الـ Frontend (HTML + CSS + JavaScript المطور بالكامل)
# =====================================================================
HTML_PAGE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>Bobos PS Management System</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #1a1a2e; color: #fff; margin: 0; padding: 10px; }
        .tabs { display: flex; justify-content: center; background: #16213e; padding: 10px; border-radius: 8px; margin-bottom: 20px; }
        .tab-btn { background: none; border: none; color: #fff; font-size: 18px; padding: 10px 25px; cursor: pointer; font-weight: bold; }
        .tab-btn.active { color: #e94560; border-bottom: 3px solid #e94560; }
        .content-section { display: none; }
        .content-section.active { display: block; }
        
        /* شاشة الكاشير والمربعات */
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 20px; }
        .card { background: #16213e; border-radius: 10px; padding: 15px; border: 1px solid #0f3460; box-shadow: 0 4px 10px rgba(0,0,0,0.3); position: relative; }
        .card h3 { margin: 0 0 10px 0; color: #4ecc71; text-align: center; }
        .status-tag { text-align: center; font-weight: bold; padding: 5px; border-radius: 5px; margin-bottom: 10px; }
        .Available { background: #2ecc71; color: #fff; }
        .Playing { background: #e74c3c; color: #fff; }
        
        /* العداد الحي */
        .timer-display { background: #0f3460; font-size: 22px; font-weight: bold; text-align: center; color: #f1c40f; padding: 8px; border-radius: 5px; margin-bottom: 10px; font-family: monospace; }
        
        .control-group { display: flex; gap: 5px; margin-bottom: 10px; }
        select, input, button { padding: 8px; border-radius: 5px; border: none; font-family: inherit; }
        button { cursor: pointer; font-weight: bold; background: #e94560; color: white; }
        button:hover { opacity: 0.9; }
        .btn-success { background: #2ecc71; }
        .btn-warning { background: #f39c12; }
        .btn-transfer { background: #3498db; }
        .btn-del { background: #c0392b; padding: 4px 10px; font-size: 13px; }
        .orders-list { background: #0f3460; padding: 8px; border-radius: 5px; font-size: 13px; max-height: 100px; overflow-y: auto; margin-top: 10px; }
        .order-item { display: flex; justify-content: space-between; margin-bottom: 3px; align-items: center; }

        /* شاشة لوحة التحكم - الأدمن */
        .admin-box { background: #16213e; padding: 20px; border-radius: 10px; margin-bottom: 20px; border: 1px solid #0f3460; }
        .admin-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        .form-group { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
        .form-group input { background: #0f3460; color: white; padding: 8px; border-radius: 5px; border: none; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 10px; text-align: right; border-bottom: 1px solid #0f3460; }
        th { background: #0f3460; color: #e94560; }
        
        /* نافذة الفاتورة المنبثقة */
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); justify-content: center; align-items: center; z-index: 999; }
        .invoice-box { background: #fff; color: #000; padding: 25px; border-radius: 8px; width: 350px; box-shadow: 0 0 20px rgba(255,255,255,0.2); }
        .invoice-box h2 { text-align: center; color: #1a1a2e; margin-top: 0; border-bottom: 2px dashed #000; padding-bottom: 10px; }
        .invoice-row { display: flex; justify-content: space-between; margin: 8px 0; font-size: 15px; }
        .total-row { font-weight: bold; border-top: 2px dashed #000; padding-top: 10px; font-size: 18px; }
    </style>
</head>
<body>

    <div class="tabs">
        <button id="btn-tab-user" class="tab-btn active" onclick="switchTab('user-section')">📱 شاشة الكاشير (User)</button>
        <button id="btn-tab-admin" class="tab-btn" onclick="verifyAdminAccess()">⚙️ إعدادات النظام (Admin)</button>
    </div>

    <div id="user-section" class="content-section active">
        <div class="grid" id="user-devices-container"></div>
    </div>

    <div id="admin-section" class="content-section">
        <div class="admin-grid">
            <div class="admin-box">
                <h3>➕ إضافة جهاز جديد</h3>
                <div class="form-group"><label>اسم الجهاز:</label><input type="text" id="adm-dev-name"></div>
                <div class="form-group"><label>سعر الساعة فردي:</label><input type="number" id="adm-dev-single"></div>
                <div class="form-group"><label>سعر الساعة زوجي:</label><input type="number" id="adm-dev-multi"></div>
                <button class="btn-success" onclick="addDevice()">حفظ الجهاز</button>
            </div>
            <div class="admin-box">
                <h3>🥤 إضافة مشروب / تسالي للمنيو</h3>
                <div class="form-group"><label>اسم المشروب:</label><input type="text" id="adm-drink-name"></div>
                <div class="form-group"><label>السعر (جنيه):</label><input type="number" id="adm-drink-price"></div>
                <button class="btn-success" onclick="addDrink()">حفظ المشروب</button>
            </div>
        </div>
        <div class="admin-grid" style="margin-top: 20px;">
            <div class="admin-box">
                <h3>📋 الأجهزة الحالية وإدارتها</h3>
                <table id="adm-table-devices"><thead><tr><th>الجهاز</th><th>فردي</th><th>زوجي</th><th>التحكم</th></tr></thead><tbody></tbody></table>
            </div>
            <div class="admin-box">
                <h3>📋 قائمة المنيو الحالية</h3>
                <table id="adm-table-drinks"><thead><tr><th>المشروب</th><th>السعر</th><th>التحكم</th></tr></thead><tbody></tbody></table>
            </div>
        </div>
    </div>

    <div class="modal" id="invoice-modal">
        <div class="invoice-box">
            <h2>فاتورة بيبو سيستم</h2>
            <div id="invoice-details"></div>
            <button style="width:100%; margin-top:15px; font-size:16px;" onclick="closeInvoice()">إغلاق وطباعة الفاتورة</button>
        </div>
    </div>

    <script>
        let allDrinks = [];
        let devicesData = [];

        // 1. قفل الأمان بالباسورد لحماية الأسعار والإعدادات
        async function verifyAdminAccess() {
            const password = prompt("برجاء إدخال كلمة مرور مدير النظام لفتح الإعدادات:");
            if (!password) return;
            
            const res = await fetch('/api/admin/verify', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ password: password })
            });
            const data = await res.json();
            
            if (data.authenticated) {
                switchTab('admin-section');
                document.getElementById('btn-tab-admin').classList.add('active');
                document.getElementById('btn-tab-user').classList.remove('active');
            } else {
                alert("❌ كلمة المرور خاطئة! لا يمكن الدخول وتعديل الأسعار.");
            }
        }

        function switchTab(tabId) {
            document.querySelectorAll('.content-section').forEach(s => s.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            if(tabId === 'admin-section') loadAdminData();
        }

        // 2. تحديث وبناء واجهة الأجهزة الحية للكاشير
        async function loadUserDashboard() {
            const resDrinks = await fetch('/api/drinks'); allDrinks = await resDrinks.json();
            const resDevs = await fetch('/api/devices'); devicesData = await resDevs.json();
            
            const container = document.getElementById('user-devices-container');
            container.innerHTML = '';

            // تجميع خيارات الأجهزة المتاحة حالياً للنقل إليها
            let availableOptions = devicesData.filter(d => d.status === 'Available').map(d => `<option value="${d.name}">${d.name}</option>`).join('');

            devicesData.forEach(dev => {
                const card = document.createElement('div');
                card.className = 'card';
                
                let timerHTML = '';
                let controlsHTML = '';
                let drinksHTML = '';

                if (dev.status === 'Available') {
                    controlsHTML = `
                        <div class="control-group">
                            <select id="mode-${dev.name}" style="flex:1;">
                                <option value="single">فردي (${dev.single_price}ج/س)</option>
                                <option value="multi">زوجي (${dev.multi_price}ج/س)</option>
                            </select>
                            <button class="btn-success" onclick="startDevice('${dev.name}')">بدء اللعب</button>
                        </div>`;
                } else {
                    // العداد الحي المباشر بالثانية
                    timerHTML = `<div class="timer-display" id="timer-${dev.name.replace(/\s+/g, '')}" data-start="${dev.start_time}">00:00:00</div>`;
                    
                    let drinkOptions = allDrinks.map(d => `<option value="${d.name}">${d.name} (${d.price}ج)</option>`).join('');
                    let ordersItems = dev.orders.map(o => `
                        <div class="order-item">
                            <span>${o.drink_name} (x${o.quantity})</span>
                            <button class="btn-del" style="padding:2px 6px; font-size:11px;" onclick="removeDrinkFromDevice('${dev.name}', '${o.drink_name}')">حذف</button>
                        </div>
                    `).join('');

                    controlsHTML = `
                        <div class="control-group">
                            <select id="drink-select-${dev.name}" style="flex:1;">${drinkOptions}</select>
                            <button onclick="addDrinkToDevice('${dev.name}')">➕ مشروب</button>
                        </div>
                        
                        <div class="control-group" style="margin-top:5px;">
                            <select id="transfer-target-${dev.name}" style="flex:1;">
                                <option value="">انقل لجهاز آخر...</option>
                                ${availableOptions || '<option disabled>لا توجد أجهزة متاحة حالياً</option>'}
                            </select>
                            <button class="btn-transfer" onclick="transferDevice('${dev.name}')">🔄 نقل</button>
                        </div>

                        <button class="btn-warning" style="width:100%; margin-top:8px;" onclick="stopDevice('${dev.name}')">🛑 إنهاء الحساب والوقت</button>
                    `;

                    drinksHTML = `<div class="orders-list"><strong>🍹 طلبات الطاولة الحالية:</strong>${ordersItems || '<div style="color:#aaa;">لا يوجد طلبات</div>'}</div>`;
                }

                card.innerHTML = `
                    <h3>${dev.name}</h3>
                    <div class="status-tag ${dev.status}">${dev.status === 'Available' ? 'متاح' : 'جاري اللعب (' + (dev.mode==='single'?'فردي':'زوجي') + ')'}</div>
                    ${timerHTML}
                    ${controlsHTML}
                    ${drinksHTML}
                `;
                container.appendChild(card);
            });
            updateTimers();
        }

        // 3. دالة تشغيل وتحديث العداد الحي المباشر (Live Timer) كل ثانية
        function updateTimers() {
            const now = Math.floor(Date.now() / 1000);
            document.querySelectorAll('.timer-display').forEach(timer => {
                const startTime = parseFloat(timer.getAttribute('data-start'));
                if (!startTime) return;
                
                const elapsedSeconds = Math.max(0, now - Math.floor(startTime));
                
                const hrs = Math.floor(elapsedSeconds / 3600).toString().padStart(2, '0');
                const mins = Math.floor((elapsedSeconds % 3600) / 60).toString().padStart(2, '0');
                const secs = (elapsedSeconds % 60).toString().padStart(2, '0');
                
                timer.innerText = `${hrs}:${mins}:${secs}`;
            });
        }

        // أفعال الكاشير (المستخدم)
        async function startDevice(name) {
            const mode = document.getElementById(`mode-${name}`).value;
            await fetch('/api/start', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name, mode}) });
            loadUserDashboard();
        }

        async function transferDevice(sourceName) {
            const targetName = document.getElementById(`transfer-target-${sourceName}`).value;
            if(!targetName) { alert("من فضلك اختر جهاز متاح أولاً لنقل الفاتورة إليه!"); return; }
            
            const res = await fetch('/api/transfer', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({source: sourceName, target: targetName}) });
            const data = await res.json();
            if(data.success) {
                alert(`🔄 تم نقل الفاتورة والوقت بالكامل من ${sourceName} إلى ${targetName} بنجاح!`);
                loadUserDashboard();
            }
        }

        // 🛑 دالة إنهاء الوقت المحدثة برسالة تأكيد لحماية البيانات من الـ Misclicks
        async function stopDevice(name) {
            const confirmStop = confirm(`⚠️ هل أنت متأكد من إنهاء حساب وقت ${name} وإصدار الفاتورة النهائية؟`);
            if (!confirmStop) return; // لو ضغط إلغاء، كأن شيئاً لم يكن والوقت يستمر

            const res = await fetch('/api/stop', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name}) });
            const invoice = await res.json();
            
            let html = `
                <div class="invoice-row"><strong>الجهاز:</strong> <span>${invoice.device}</span></div>
                <div class="invoice-row"><strong>النظام:</strong> <span>${invoice.mode === 'single' ? 'فردي' : 'زوجي'}</span></div>
                <div class="invoice-row"><strong>الوقت اللعب:</strong> <span>${invoice.elapsed_time_str}</span></div>
                <div class="invoice-row"><strong>حساب الوقت:</strong> <span>${invoice.time_cost} جنيه</span></div>
                <h4 style="margin:10px 0 5px 0; border-bottom:1px solid #000; padding-bottom:5px;">🍹 المشاريب والطلبات:</h4>
            `;
            invoice.drinks.forEach(d => {
                html += `<div class="invoice-row"><span>${d.name} (x${d.qty})</span> <span>${d.total} ج</span></div>`;
            });
            html += `<div class="invoice-row total-row"><strong>الإجمالي الكلي:</strong> <span>${invoice.total_all} جنيه</span></div>`;
            
            document.getElementById('invoice-details').innerHTML = html;
            document.getElementById('invoice-modal').style.display = 'flex';
            loadUserDashboard();
        }

        function closeInvoice() { document.getElementById('invoice-modal').style.display = 'none'; }
        
        async function addDrinkToDevice(deviceName) {
            const drinkName = document.getElementById(`drink-select-${deviceName}`).value;
            await fetch('/api/device/add-drink', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({device_name: deviceName, drink_name: drinkName}) });
            loadUserDashboard();
        }
        
        async function removeDrinkFromDevice(deviceName, drinkName) {
            await fetch('/api/device/remove-drink', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({device_name: deviceName, drink_name: drinkName}) });
            loadUserDashboard();
        }

        // لوحة تحكم وإدارة بيانات الأدمن (إضافة وحذف)
        async function loadAdminData() {
            const resDevs = await fetch('/api/devices'); const devs = await resDevs.json();
            const resDrinks = await fetch('/api/drinks'); const drinks = await resDrinks.json();
            
            // جدول الأجهزة مع زرار الحذف النهائي
            document.querySelector('#adm-table-devices tbody').innerHTML = devs.map(d => `
                <tr>
                    <td>${d.name}</td>
                    <td>${d.single_price}ج</td>
                    <td>${d.multi_price}ج</td>
                    <td><button class="btn-del" onclick="deleteDevice('${d.name}')">❌ حذف</button></td>
                </tr>
            `).join('');
            
            // جدول المشاريب مع زرار الحذف من المنيو
            document.querySelector('#adm-table-drinks tbody').innerHTML = drinks.map(d => `
                <tr>
                    <td>${d.name}</td>
                    <td>${d.price}ج</td>
                    <td><button class="btn-del" onclick="deleteDrink('${d.name}')">❌ حذف</button></td>
                </tr>
            `).join('');
        }
        
        async function addDevice() {
            const name = document.getElementById('adm-dev-name').value;
            const single = document.getElementById('adm-dev-single').value;
            const multi = document.getElementById('adm-dev-multi').value;
            if(!name || !single || !multi) { alert("برجاء ملء جميع حقول الجهاز!"); return; }
            await fetch('/api/admin/add-device', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name, single, multi}) });
            loadAdminData(); alert("تم حفظ الجهاز بنجاح وجاهز للتشغيل!");
            document.getElementById('adm-dev-name').value = ''; document.getElementById('adm-dev-single').value = ''; document.getElementById('adm-dev-multi').value = '';
        }
        
        async function addDrink() {
            const name = document.getElementById('adm-drink-name').value;
            const price = document.getElementById('adm-drink-price').value;
            if(!name || !price) { alert("برجاء إدخال اسم المشروب وسعره!"); return; }
            await fetch('/api/admin/add-drink', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name, price}) });
            loadAdminData(); alert("تم حفظ المشروب وإضافته للمنيو بنجاح!");
            document.getElementById('adm-drink-name').value = ''; document.getElementById('adm-drink-price').value = '';
        }

        async function deleteDevice(name) {
            if(!confirm(`⚠️ هل أنت متأكد من حذف الجهاز "${name}" نهائياً من السيستم؟`)) return;
            await fetch('/api/admin/delete-device', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name}) });
            loadAdminData();
        }

        async function deleteDrink(name) {
            if(!confirm(`⚠️ هل أنت متأكد من حذف المشروب "${name}" من قائمة المنيو؟`)) return;
            await fetch('/api/admin/delete-drink', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name}) });
            loadAdminData();
        }

        // العدادات الحية تحدث كل ثانية، والبيانات العامة تتزامن كل 5 ثواني تلقائياً
        setInterval(updateTimers, 1000);
        setInterval(() => {
            if(document.getElementById('user-section').classList.contains('active')) loadUserDashboard();
        }, 5000);

        window.onload = loadUserDashboard;
    </script>
</body>
</html>
"""

# =====================================================================
# 3. مسارات الـ API والـ Backend (المنطق البرمجي والحسابي)
# =====================================================================
@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

@app.route('/api/admin/verify', methods=['POST'])
def verify_admin():
    data = request.json
    if data.get('password') == ADMIN_PASSWORD:
        return jsonify({"authenticated": True})
    return jsonify({"authenticated": False})

@app.route('/api/drinks', methods=['GET'])
def get_drinks():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name, price FROM drinks")
    drinks = [{"name": row[0], "price": row[1]} for row in cursor.fetchall()]
    conn.close()
    return jsonify(drinks)

@app.route('/api/devices', methods=['GET'])
def get_devices():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name, single_price, multi_price, status, start_time, mode FROM devices")
    devices = []
    for row in cursor.fetchall():
        dev_name = row[0]
        cursor.execute("SELECT drink_name, quantity FROM active_orders WHERE device_name=?", (dev_name,))
        orders = [{"drink_name": r[0], "quantity": r[1]} for r in cursor.fetchall()]
        
        devices.append({
            "name": dev_name, "single_price": row[1], "multi_price": row[2],
            "status": row[3], "start_time": row[4], "mode": row[5], "orders": orders
        })
    conn.close()
    return jsonify(devices)

@app.route('/api/start', methods=['POST'])
def start_device():
    data = request.json
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE devices SET status='Playing', start_time=?, mode=? WHERE name=?", (time.time(), data['mode'], data['name']))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# 🔄 ميزة نقل الوقت والفاتورة بالكامل لجهاز تاني متاح
@app.route('/api/transfer', methods=['POST'])
def transfer_device():
    data = request.json
    source = data['source']
    target = data['target']
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. جلب بيانات التشغيل من الجهاز القديم
    cursor.execute("SELECT start_time, mode FROM devices WHERE name=?", (source,))
    start_time, mode = cursor.fetchone()
    
    # 2. نقل البيانات وتشغيل الجهاز الجديد بنفس وقت البداية والنظام
    cursor.execute("UPDATE devices SET status='Playing', start_time=?, mode=? WHERE name=?", (start_time, mode, target))
    
    # 3. تحويل كل الطلبات والمشاريب المرتبطة بالجهاز القديم إلى الجهاز الجديد
    cursor.execute("UPDATE active_orders SET device_name=? WHERE device_name=?", (target, source))
    
    # 4. تصفير وإتاحة الجهاز القديم في نفس اللحظة
    cursor.execute("UPDATE devices SET status='Available', start_time=NULL WHERE name=?", (source,))
    
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/stop', methods=['POST'])
def stop_device():
    data = request.json
    name = data['name']
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT start_time, mode, single_price, multi_price FROM devices WHERE name=?", (name,))
    start_time, mode, single_price, multi_price = cursor.fetchone()
    
    elapsed_seconds = time.time() - start_time if start_time else 0
    hrs = int(elapsed_seconds // 3600)
    mins = int((elapsed_seconds % 3600) // 60)
    elapsed_time_str = f"{hrs} ساعة و {mins} دقيقة"
    
    # حساب تكلفة الوقت بالدقائق الفردية والزوجية
    elapsed_minutes = max(1, elapsed_seconds / 60)
    hourly_rate = single_price if mode == 'single' else multi_price
    time_cost = round((elapsed_minutes / 60) * hourly_rate, 2)
    
    # حساب تكلفة المشاريب والطلبات
    cursor.execute("""SELECT active_orders.drink_name, active_orders.quantity, drinks.price 
                      FROM active_orders 
                      JOIN drinks ON active_orders.drink_name = drinks.name 
                      WHERE active_orders.device_name=?""", (name,))
    
    drinks_invoice = []
    drinks_total = 0
    for r in cursor.fetchall():
        tot = r[1] * r[2]
        drinks_total += tot
        drinks_invoice.append({"name": r[0], "qty": r[1], "total": tot})
        
    total_all = round(time_cost + drinks_total, 2)
    
    # تصفير وإتاحة الجهاز ومسح طلباته بعد استخراج الحساب
    cursor.execute("UPDATE devices SET status='Available', start_time=NULL WHERE name=?", (name,))
    cursor.execute("DELETE FROM active_orders WHERE device_name=?", (name,))
    conn.commit()
    conn.close()
    
    return jsonify({
        "device": name, "mode": mode, "elapsed_time_str": elapsed_time_str,
        "time_cost": time_cost, "drinks": drinks_invoice, "total_all": total_all
    })

@app.route('/api/device/add-drink', methods=['POST'])
def add_drink_to_device():
    data = request.json
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, quantity FROM active_orders WHERE device_name=? AND drink_name=?", (data['device_name'], data['drink_name']))
    row = cursor.fetchone()
    if row:
        cursor.execute("UPDATE active_orders SET quantity=? WHERE id=?", (row[1]+1, row[0]))
    else:
        cursor.execute("INSERT INTO active_orders (device_name, drink_name, quantity) VALUES (?, ?, 1)", (data['device_name'], data['drink_name']))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/device/remove-drink', methods=['POST'])
def remove_drink_from_device():
    data = request.json
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, quantity FROM active_orders WHERE device_name=? AND drink_name=?", (data['device_name'], data['drink_name']))
    row = cursor.fetchone()
    if row:
        if row[1] > 1:
            cursor.execute("UPDATE active_orders SET quantity=? WHERE id=?", (row[1]-1, row[0]))
        else:
            cursor.execute("DELETE FROM active_orders WHERE id=?", (row[0],))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/add-device', methods=['POST'])
def admin_add_device():
    data = request.json
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO devices (name, single_price, multi_price) VALUES (?, ?, ?)", (data['name'], data['single'], data['multi']))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/add-drink', methods=['POST'])
def admin_add_drink():
    data = request.json
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO drinks (name, price) VALUES (?, ?)", (data['name'], data['price']))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# ❌ مسار حذف جهاز من السيستم للأدمن
@app.route('/api/admin/delete-device', methods=['POST'])
def admin_delete_device():
    data = request.json
    name = data['name']
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM devices WHERE name=?", (name,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# ❌ مسار حذف مشروب من المنيو للأدمن
@app.route('/api/admin/delete-drink', methods=['POST'])
def admin_delete_drink():
    data = request.json
    name = data['name']
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM drinks WHERE name=?", (name,))
    cursor.execute("DELETE FROM active_orders WHERE drink_name=?", (name,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

def run_server():
    # كتم مخرجات السيرفر للحفاظ على سرعة الـ EXE ونظافته
    sys.stdout = open(os.devnull, 'w')
    sys.stderr = open(os.devnull, 'w')
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)

# =====================================================================
# 4. تشغيل واجهة المستخدم المدمجة والنظام
# =====================================================================
if __name__ == '__main__':
    init_db()
    
    server_thread = Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    
    time.sleep(1)
    
    # فتح نافذة السيستم كبرنامج مستقل شيك ومقفل
    webview.create_window("Bobos PS System v3.5", "http://127.0.0.1:5000/")
    webview.start()