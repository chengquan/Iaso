import time
import machine
import uarray

class LongScanChainTester:
    def __init__(self, sc_len=50000):
        """
        初始化长扫描链测试器
        参数:
            sc_len: 扫描链长度
        """
        # 根据提供的引脚配置初始化
        self.SCAN_IN = machine.Pin(7, machine.Pin.OUT)
        self.SCAN_OUT = machine.Pin(21, machine.Pin.IN)
        self.SCAN_EN = machine.Pin(22, machine.Pin.OUT)
        self.SCAN_CLK = machine.Pin(2, machine.Pin.OUT)
        self.SC_LEN = sc_len
        
        # 初始化引脚状态
        self.SCAN_EN.off()
        self.SCAN_CLK.off()
        self.SCAN_IN.off()
        
        # 使用更紧凑的数据结构存储错误信息
        self.error_count = 0
        self.last_error_time = 0
        self.error_bit_positions = uarray.array('H')  # 16位无符号整数数组，存储错误位位置
        
        # 性能监控
        self.operations_count = 0
        self.start_time = time.ticks_ms()
        
    def _pulse_clock(self):
        """产生时钟脉冲"""
        self.SCAN_CLK.on()
        # 对于长扫描链，使用最小延时
        time.sleep_us(1)
        self.SCAN_CLK.off()
        time.sleep_us(1)
        
    def write_alternating_pattern(self):
        """
        写入交替模式 (010101...) 到扫描链
        直接写入，不存储整个模式
        """
        self.SCAN_EN.on()  # 启用扫描链
        
        # 直接生成交替模式并写入，避免存储整个模式
        for i in range(self.SC_LEN):
            bit = 1 if (i % 2 == 0) else 0
            self.SCAN_IN.value(bit)
            self._pulse_clock()
        
        self.SCAN_EN.off()  # 禁用扫描链
        self.operations_count += 1
        
    def read_and_verify_scan_chain(self):
        """
        读取并验证扫描链数据
        关键修正：在读取的同时将数据写回，保持扫描链内容不变
        返回: (has_errors, error_bits)
        """
        self.SCAN_EN.on()  # 启用扫描链
        
        error_bits = []
        current_bit_positions = uarray.array('H')  # 临时存储错误位位置
        
        # 逐位读取并验证，同时将读取的数据写回
        for i in range(self.SC_LEN):
            expected_bit = 1 if (i % 2 == 0) else 0
            actual_bit = self.SCAN_OUT.value()
            
            # 检查是否发生翻转
            if expected_bit != actual_bit:
                current_bit_positions.append(i)
            
            # 关键修正：将读取的位写回扫描链，保持内容不变
            self.SCAN_IN.value(actual_bit)
            self._pulse_clock()
        
        self.SCAN_EN.off()  # 禁用扫描链
        self.operations_count += 1
        
        has_errors = len(current_bit_positions) > 0
        return has_errors, current_bit_positions
    
    def log_error_summary(self, error_bits, current_time):
        """记录错误摘要，避免存储过多数据"""
        error_count_this_time = len(error_bits)
        self.error_count += error_count_this_time
        self.last_error_time = current_time
        
        # 只存储前100个错误位置，避免内存耗尽
        if len(self.error_bit_positions) < 100:
            for pos in error_bits:
                if len(self.error_bit_positions) < 100:
                    self.error_bit_positions.append(pos)
        
        # 打印错误摘要
        print(f"SEU Error detected at {current_time}ms")
        print(f"  Total bits flipped: {error_count_this_time}")
        if error_count_this_time <= 10:
            print(f"  Flipped bit positions: {error_bits}")
        else:
            print(f"  First 10 flipped bits: {error_bits[:10]}")
        
    def test_seu_reliability(self, test_duration_ms=60000, check_interval_ms=5000):
        """
        测试长扫描链的SEU可靠性
        参数:
            test_duration_ms: 测试总时长（毫秒）
            check_interval_ms: 检查间隔（毫秒）
        """
        print(f"Starting SEU reliability test for {self.SC_LEN}-bit scan chain")
        print(f"Test duration: {test_duration_ms}ms")
        print(f"Check interval: {check_interval_ms}ms")
        print("Pin configuration:")
        print(f"  SCAN_IN:  GPIO{self.SCAN_IN}")
        print(f"  SCAN_OUT: GPIO{self.SCAN_OUT}")
        print(f"  SCAN_EN:  GPIO{self.SCAN_EN}")
        print(f"  SCAN_CLK: GPIO{self.SCAN_CLK}")
        print()
        
        # 初始写入交替模式
        print("Writing alternating pattern (010101...) to scan chain")
        start_write_time = time.ticks_ms()
        self.write_alternating_pattern()
        write_time = time.ticks_diff(time.ticks_ms(), start_write_time)
        print(f"Initial pattern written in {write_time}ms")
        print()
        
        start_time = time.ticks_ms()
        last_check_time = start_time
        last_status_time = start_time
        
        while time.ticks_diff(time.ticks_ms(), start_time) < test_duration_ms:
            current_time = time.ticks_ms()
            
            # 定期打印状态信息
            if time.ticks_diff(current_time, last_status_time) >= 10000:  # 每10秒
                elapsed = time.ticks_diff(current_time, start_time)
                print(f"Test progress: {elapsed/1000:.1f}s / {test_duration_ms/1000:.1f}s")
                print(f"Operations performed: {self.operations_count}")
                print(f"Total errors so far: {self.error_count}")
                if self.error_count > 0:
                    print(f"Last error at: {self.last_error_time}ms")
                print()
                last_status_time = current_time
            
            # 检查是否到达检查间隔
            if time.ticks_diff(current_time, last_check_time) >= check_interval_ms:
                # 读取并验证扫描链
                start_check_time = time.ticks_ms()
                has_errors, error_bits = self.read_and_verify_scan_chain()
                check_time = time.ticks_diff(time.ticks_ms(), start_check_time)
                
                if has_errors:
                    # 记录错误
                    self.log_error_summary(error_bits, current_time)
                    
                    # 重新写入正确数据
                    self.write_alternating_pattern()
                    print("Corrected scan chain data")
                    print()
                else:
                    print(f"Check at {current_time}ms: No errors (check took {check_time}ms)")
                
                last_check_time = current_time
            
            # 短暂延时，避免过度占用CPU
            time.sleep_ms(10)
        
        # 测试结束，打印统计信息
        elapsed_time = time.ticks_diff(time.ticks_ms(), start_time)
        self.print_final_report(elapsed_time)
    
    def print_final_report(self, elapsed_time):
        """打印最终测试报告"""
        print("=" * 60)
        print("SEU Reliability Test Results - Long Scan Chain")
        print("=" * 60)
        print(f"Scan chain length: {self.SC_LEN} bits")
        print(f"Total test duration: {elapsed_time}ms ({elapsed_time/1000:.2f}s)")
        print(f"Total operations: {self.operations_count}")
        print(f"Total errors detected: {self.error_count}")
        
        if elapsed_time > 0:
            error_rate = self.error_count / (elapsed_time / 1000)
            print(f"Error rate: {error_rate:.6f} errors/second")
            
            if self.error_count > 0:
                bit_error_rate = self.error_count / (self.operations_count * self.SC_LEN)
                print(f"Bit error rate: {bit_error_rate:.9f}")
        
        if self.error_count > 0:
            print(f"Last error occurred at: {self.last_error_time}ms")
            if len(self.error_bit_positions) > 0:
                print(f"Sample error positions: {self.error_bit_positions[:10]}")
                if len(self.error_bit_positions) > 10:
                    print(f"  ... and {len(self.error_bit_positions) - 10} more positions")
        
        # 性能统计
        if elapsed_time > 0:
            operations_per_sec = self.operations_count / (elapsed_time / 1000)
            print(f"Operations per second: {operations_per_sec:.2f}")
            bits_per_sec = (self.operations_count * self.SC_LEN) / (elapsed_time / 1000)
            print(f"Bits processed per second: {bits_per_sec:.2f}")

# 使用示例
if __name__ == "__main__":
    # 创建测试器实例
    # 扫描链长度50000位
    tester = LongScanChainTester(sc_len=50000)
    
    # 运行SEU可靠性测试
    # 对于5万位扫描链，使用较长的检查间隔(5秒)
    tester.test_seu_reliability(test_duration_ms=120000, check_interval_ms=5000)