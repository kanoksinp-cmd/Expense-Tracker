<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Expense Tracker Web App</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body class="bg-gray-100 font-sans">

    <div class="max-w-4xl mx-auto p-5">
        <header class="text-center mb-10">
            <h1 class="text-3xl font-bold text-gray-800">💰 บันทึกรายรับ-รายจ่าย</h1>
            <p class="text-gray-500">เวอร์ชัน Web Browser (Local Storage)</p>
        </header>

        <!-- ส่วนสรุปยอด -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
            <div class="bg-green-100 p-5 rounded-lg border-l-4 border-green-500">
                <p class="text-sm text-green-600 uppercase">รายรับทั้งหมด</p>
                <p id="total-income" class="text-2xl font-bold">฿0.00</p>
            </div>
            <div class="bg-red-100 p-5 rounded-lg border-l-4 border-red-500">
                <p class="text-sm text-red-600 uppercase">รายจ่ายทั้งหมด</p>
                <p id="total-expense" class="text-2xl font-bold">฿0.00</p>
            </div>
            <div class="bg-blue-100 p-5 rounded-lg border-l-4 border-blue-500">
                <p class="text-sm text-blue-600 uppercase">ยอดคงเหลือ</p>
                <p id="total-balance" class="text-2xl font-bold">฿0.00</p>
            </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
            <!-- ฟอร์มกรอกข้อมูล -->
            <div class="bg-white p-6 rounded-lg shadow-md">
                <h2 class="text-xl font-semibold mb-4">📝 เพิ่มรายการ</h2>
                <form id="transaction-form">
                    <div class="mb-4">
                        <label class="block text-sm font-medium">วันที่</label>
                        <input type="date" id="date" class="w-full border p-2 rounded mt-1" required>
                    </div>
                    <div class="mb-4">
                        <label class="block text-sm font-medium">ประเภท</label>
                        <select id="type" class="w-full border p-2 rounded mt-1">
                            <option value="income">รายรับ</option>
                            <option value="expense">รายจ่าย</option>
                        </select>
                    </div>
                    <div class="mb-4">
                        <label class="block text-sm font-medium">หมวดหมู่</label>
                        <input type="text" id="category" placeholder="เช่น อาหาร, เงินเดือน" class="w-full border p-2 rounded mt-1" required>
                    </div>
                    <div class="mb-4">
                        <label class="block text-sm font-medium">จำนวนเงิน</label>
                        <input type="number" id="amount" step="0.01" class="w-full border p-2 rounded mt-1" required>
                    </div>
                    <button type="submit" class="w-full bg-blue-600 text-white py-2 rounded hover:bg-blue-700">บันทึกรายการ</button>
                </form>
            </div>

            <!-- กราฟสรุป -->
            <div class="bg-white p-6 rounded-lg shadow-md">
                <h2 class="text-xl font-semibold mb-4">📊 สัดส่วนรายจ่าย</h2>
                <canvas id="expenseChart"></canvas>
            </div>
        </div>

        <!-- ตารางแสดงรายการ -->
        <div class="mt-10 bg-white p-6 rounded-lg shadow-md overflow-x-auto">
            <h2 class="text-xl font-semibold mb-4">📜 ประวัติรายการ</h2>
            <table class="w-full text-left">
                <thead>
                    <tr class="border-b">
                        <th class="p-2">วันที่</th>
                        <th class="p-2">หมวดหมู่</th>
                        <th class="p-2">ประเภท</th>
                        <th class="p-2 text-right">จำนวนเงิน</th>
                    </tr>
                </thead>
                <tbody id="transaction-list">
                    <!-- ข้อมูลจะถูกเติมด้วย JavaScript -->
                </tbody>
            </table>
        </div>
    </div>

    <script>
        let transactions = JSON.parse(localStorage.getItem('transactions')) || [];

        const form = document.getElementById('transaction-form');
        const list = document.getElementById('transaction-list');
        const incomeEl = document.getElementById('total-income');
        const expenseEl = document.getElementById('total-expense');
        const balanceEl = document.getElementById('total-balance');

        function updateUI() {
            list.innerHTML = '';
            let income = 0;
            let expense = 0;

            transactions.forEach((t, index) => {
                const row = document.createElement('tr');
                row.className = "border-b text-sm";
                row.innerHTML = `
                    <td class="p-2">${t.date}</td>
                    <td class="p-2">${t.category}</td>
                    <td class="p-2 ${t.type === 'income' ? 'text-green-600' : 'text-red-600'}">${t.type === 'income' ? 'รายรับ' : 'รายจ่าย'}</td>
                    <td class="p-2 text-right">${parseFloat(t.amount).toLocaleString()}</td>
                `;
                list.appendChild(row);

                if (t.type === 'income') income += parseFloat(t.amount);
                else expense += parseFloat(t.amount);
            });

            incomeEl.innerText = `฿${income.toLocaleString()}`;
            expenseEl.innerText = `฿${expense.toLocaleString()}`;
            balanceEl.innerText = `฿${(income - expense).toLocaleString()}`;
            
            updateChart();
            localStorage.setItem('transactions', JSON.stringify(transactions));
        }

        form.addEventListener('submit', (e) => {
            e.preventDefault();
            const newTransaction = {
                date: document.getElementById('date').value,
                type: document.getElementById('type').value,
                category: document.getElementById('category').value,
                amount: document.getElementById('amount').value
            };
            transactions.push(newTransaction);
            form.reset();
            updateUI();
        });

        // ระบบกราฟ (Chart.js)
        let myChart;
        function updateChart() {
            const ctx = document.getElementById('expenseChart').getContext('2d');
            const expensesOnly = transactions.filter(t => t.type === 'expense');
            const categories = [...new Set(expensesOnly.map(t => t.category))];
            const data = categories.map(cat => {
                return expensesOnly.filter(t => t.category === cat).reduce((sum, t) => sum + parseFloat(t.amount), 0);
            });

            if (myChart) myChart.destroy();
            myChart = new Chart(ctx, {
                type: 'pie',
                data: {
                    labels: categories,
                    datasets: [{
                        data: data,
                        backgroundColor: ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF']
                    }]
                }
            });
        }

        updateUI(); // รันครั้งแรกเมื่อโหลดหน้าเว็บ
    </script>
</body>
</html>
