; Remedy CPU / TinyCPU ruleset
;
; Current hardware summary:
; - 16-bit CPU. All normal RAM/flash accesses are 16-bit half-word accesses.
; - CPU addresses are word addresses. External memory byte address = {prefix, cpu_addr, 1'b0}.
; - Flash is read through QSPI continuous-read mode.
; - RAM is read/written through plain SPI mode.
; - Usable external word address range is 0x0000-0xFFFF, mapping to byte range 0x00000-0x1FFFF.
;
; Immediate behavior:
; - Any fetched word with bit15 = 1 is treated as an immediate word.
; - The immediate word updates the immediate register and is not executed as a normal opcode.
; - The following real instruction can consume that immediate value.
;
; Timers:
; - timer1 is 16-bit.
; - timer2 is 9-bit in the current RTL, even though it is the tiny timer.
; - Timer config bits:
;       bit0    enable
;       bits4:1 prescaler select
;       bit5    auto reload
;       bit6    interrupt enable
;       bit7    source select: 0 = system clock, 1 = execute_pulse
; - Prescaler values:
;       0=/1, 1=/2, 2=/4, 3=/8, 4=/16, 5=/32,
;       6=/64, 7=/128, 8=/256, 9=/512, 10=/1024, 11=/2048
; - Values 12-15 are reserved/currently behave like /1 in the RTL.
; - At 25 MHz, system-clock /2048 gives 81.92 us per timer tick.
; - If execute_pulse happens every 15 clocks, execute-source /2048 gives 1.2288 ms per timer tick.
;
; Interrupts:
; - Fixed interrupt vector: 0x0002.
; - Use reti to return.
; - Current interrupt sources:
;       bit0 = timer1
;       bit1 = timer2
;       bit2 = I2C
; - CpuinterruptEnable write bit0 = global enable.
; - InputInterruptEnable is now really the IRQ source-enable mask register.
; - InterruptRegister is the pending register. Write 1s to clear pending bits.
; - Interrupts are blocked while an immediate word is active, so an IRQ should not split imm + use-imm.
;
; I2C:
; - Small fixed-speed I2C master.
; - I2cDivider/I2cPrescaler address reads fixed divider value 20.
; - Approx SCL at 25 MHz: clk / (3 * (20 + 1)) ~= 397 kHz.
;
; Debugger:
; - Debug frame: 0xA5 sync + 4-bit cmd + 4-bit addr + 16-bit data.
; - Commands: 0=ping, 1=read debug reg, 2=write debug reg.
; - Debug core supports halt/run/step, one dynamic breakpoint, static brk, and jump/load-PC.
;
;---------- MEMORY-MAPPED REGISTERS -------------
; GPIO Registers
InputReg = 0                   ; 16-bit read, lower 8 bits are external/debug input pins
OutputReg = 1                  ; 8-bit output register

; Timer 1: 16-bit
; Timer config bits: [7]=source_execute, [6]=irq_en, [5]=auto_reload, [4:1]=prescaler, [0]=enable
timer1Config = 2
timer1Target = 3               ; 16-bit target value. target=0 disables match.
timer1Reset = 4                ; write bit0=1 to reset timer1 and clear its config
timer1ReadAdr = 5              ; read 16-bit count

; Timer 2: 9-bit tiny timer in current RTL
; Same config layout as timer1
timer2Config = 6
timer2Target = 7               ; 9-bit target value. target=0 disables match.
timer2Reset = 8                ; write bit0=1 to reset timer2 and clear its config
timer2ReadAdr = 9              ; read 9-bit count, zero-extended

timerSyncStart = 10            ; write bit0 to update enable bit of both timers at the same time

; random number generator
; RNG is always active at every clock cycle
RandomSeedAddr = 11            ; write 8-bit seed
RandomReg = 12                 ; read generated random value

; Interrupt registers
CpuinterruptEnable = 13        ; write bit0 global enable. read bit0 global, bit1 irq_lock, bit2 intr
InputInterruptEnable = 14      ; legacy name: IRQ source enable mask. bit0 timer1, bit1 timer2, bit2 I2C
InterruptRegister = 15         ; pending IRQ bits. write 1s to clear pending bits

; I2C registers
I2cCtrl = 16                   ; bit0 enable, bit1 irq enable
I2cStatus = 17                 ; bit0 busy, bit1 bus_active, bit2 done, bit3 ack_error, bit4 rx_valid, bit5 irq/done
I2cDivider = 18                ; read-only fixed divider value, currently 20
I2cPrescaler = 18              ; legacy alias for I2cDivider. Writes are ignored by current RTL.
I2cDataReg = 19                ; write TX byte / read RX byte
I2cCommand = 20                ; bit0 START, bit1 STOP, bit2 WRITE, bit3 READ, bit4 NACK-after-read

;---------- TIMER CONFIG HELPERS -------------
TimerEnableBit = 0
TimerPrescalerShift = 1
TimerReloadBit = 5
TimerIrqEnableBit = 6
TimerSourceExecuteBit = 7

; Prescaler encoding
TimerDiv1    = 0
TimerDiv2    = 1
TimerDiv4    = 2
TimerDiv8    = 3
TimerDiv16   = 4
TimerDiv32   = 5
TimerDiv64   = 6
TimerDiv128  = 7
TimerDiv256  = 8
TimerDiv512  = 9
TimerDiv1024 = 10
TimerDiv2048 = 11

; Configuration for CustomAssembly to how to compile
#bankdef data
{
    #bits 16
    #outp 0
}
#subruledef timers
{
    timer1 => 5
    timer2 => 9
}
#subruledef registers
{
    r0  => 0
    r1  => 1
    r2  => 2
    r3  => 3
    r4  => 4
    r5  => 5
    r6  => 6
    r7  => 7
    r8  => 8
    r9  => 9
    r10 => 0xa
    r11 => 0xb
    r12 => 0xc
    r13 => 0xd          ; bp
    r14 => 0xe          ; sp
    r15 => 0xf          ; ra
    BP => 0xd           ; branch pointer
    SP => 0xe           ; stack pointer
    RA => 0xf           ; return addres

}

#ruledef
{

    ;todo add an instruction to store program counter that doesnt jump
    ;______________________________________________________________________
    ; Does nothing.
    nop => 0x0000
    ;______________________________________________________________________
    ; Move the content of Rs to register Rd
    mov {rd:registers}, {rs:registers} => 0x01 @rd`4 @rs`4
    ;______________________________________________________________________
    ; Adds the content of register Rs or an immediate constant [value] to register Rd without carry.
    add {rd:registers}, {rs:registers} => 0x02 @rd`4 @rs`4
    add {rd:registers}, {value: u4} =>
    {
        0x0c @rd`4 @value`4
    }
    add {rd:registers}, {value:i16} =>
    {
        lv = value[15:15]
        (0x8000 | value)`16 @0x0b @rd`4 @lv`4
    }
    ;______________________________________________________________________
    ; Adds the content of register Rs or an immediate constant [value] to register Rd with carry.
    adc {rd:registers}, {rs:registers} => 0x03 @rd`4 @rs`4
    adc {rd:registers}, {value: u4} =>
    {
        0x0e @rd`4 @value`4
    }
    adc {rd:registers}, {value:i16} =>
    {   
        lv = value[15:15]
        (0x8000 | value)`16 @0x0d @rd`4 @lv`4
    }
    ;______________________________________________________________________
    ; Subtracts the content of register Rs or an immediate constant [value] from register Rd without carry.
    sub {rd:registers}, {rs:registers} => 0x04 @rd`4 @rs`4
    sub {rd:registers}, {value: u4} =>
    {
        0x10 @rd`4 @value`4
    }
    sub {rd:registers}, {value:i16} =>
    {   
        lv = value[15:15]
        (0x8000 | value)`16 @0x0f @rd`4 @lv`4
    }
    ;______________________________________________________________________
    ; Subtracts the content of register Rs or an immediate constant [value] from register Rd with carry.
    sbc {rd:registers}, {rs:registers} => 0x05 @rd`4 @rs`4
    sbc {rd:registers}, {value: u4} =>
    {
        0x12 @rd`4 @value`4
    }
    sbc {rd:registers}, {value:i16} =>
    {   
        lv = value[15:15]
        (0x8000 | value)`16 @0x11 @rd`4 @lv`4
    }
    ;______________________________________________________________________
    ; Performs a bitwise AND between Rd and Rs or an immediate constant [value], and stores the result in Rd.
    and {rd:registers}, {rs:registers} => 0x06 @rd`4 @rs`4
    and {rd:registers}, {value: u4} =>
    {
        0x15 @rd`4 @value`4
    }
    and {rd:registers}, {value:i16} =>
    {   
        lv = value[15:15]
        (0x8000 | value)`16 @0x14 @rd`4 @lv`4
    }
    ;______________________________________________________________________
    ; Performs a bitwise OR between Rd and Rs or an immediate constant [value], and stores the result in Rd.
    or  {rd:registers}, {rs:registers} => 0x07 @rd`4 @rs`4
    or  {rd:registers}, {value: u4} =>
    {
        0x17 @rd`4 @value`4
    }
    or  {rd:registers}, {value:i16} =>
    {   
        lv = value[15:15]
        (0x8000 | value)`16 @0x16 @rd`4 @lv`4
    }
    ;______________________________________________________________________
    ; Performs a bitwise XOR between Rd and Rs or an immediate constant [value], and stores the result in Rd.
    xor {rd:registers}, {rs:registers} => 0x08 @rd`4 @rs`4
    xor {rd:registers}, {value: u4} =>
    {
    0x19 @rd`4 @value`4
    }
    xor {rd:registers}, {value:i16} =>
    {   
        lv = value[15:15]
        (0x8000 | value)`16 @0x18 @rd`4 @lv`4
    }
    ;______________________________________________________________________
    ;Loads Register Rd with the constant value [value].
    ldi {rd:registers}, {value: u4} =>
    {
    0x0a @rd`4 @value`4
    }
    ldi {rd:registers}, {value:i16} =>
    {   
        lv = value[15:15]
        (0x8000 | value)`16 @0x09 @rd`4 @lv`4
    }
    ;______________________________________________________________________
    ;Stores the two's complement of Rd in register Rd.
    neg {rd:registers} => 0x13 @rd`4 @0`4
    ;______________________________________________________________________
    ;Stores not Rd in register Rd.
    not {rd:registers} => 0x1a @rd`4 @0`4
    ;______________________________________________________________________
    ;
    ;
    ; There were once a multiplication and a division
    ; But it doesn't fit to the chip :(
    ;
    ;
    ;______________________________________________________________________
    ; Compares Rd, and Rs or an immediate constant [value] (subtracts Rs from Rd without storing the result) Without using carry flag.
    ; Flags are updated accordingly.
    cmp {rd:registers}, {rs:registers} => 0x1e @rd`4 @rs`4
    cmp {rd:registers}, {value: u4} =>
    {
        0x21 @rd`4 @value`4
    }
    cmp {rd:registers}, {value:i16} =>
    {   
        lv = value[15:15]
        (0x8000 | value)`16 @0x20 @rd`4 @lv`4
    }
    ;______________________________________________________________________
    ; Compares Rd, and Rs or an immediate constant [value] (subtracts Rs from Rd without storing the result) With carry flag.
    ; Flags are updated accordingly.
    cpc {rd:registers}, {rs:registers} => 0x1f @rd`4 @rs`4
    cpc {rd:registers}, {value: u4} =>
    {
        0x23 @rd`4 @value`4
    }
    cpc {rd:registers}, {value:i16} =>
    {   
        lv = value[15:15]
        (0x8000 | value)`16 @0x22 @rd`4 @lv`4
    }
    ;______________________________________________________________________

    ;Shifts register Rd by one bit to the left. A zero bit is filled in and the highest bit is moved to the carry bit.
    lsl {rd:registers} => 0x24 @rd`4 @0`4

    ;Shifts register Rd by one bit to the right. A zero bit is filled in and the lowest bit is moved to the carry bit.
    lsr {rd:registers} => 0x25 @rd`4 @0`4

    ;Shifts register Rd by one bit to the left. The carry bit is filled in and the highest bit is moved to the carry bit.
    rol {rd:registers} => 0x26 @rd`4 @0`4

    ;Shifts register Rd by one bit to the right. The carry bit is filled in and the lowest bit is moved to the carry bit.
    ror {rd:registers} => 0x27 @rd`4 @0`4

    ;Shifts register Rd by one bit to the right. The MSB
    ;remains unchanged and the lowest bit is moved to the carry bit
    asr {rd:registers} => 0x28 @rd`4 @0`4

    ;Swaps the high and low byte in register Rd.
    swap {rd:registers} => 0x29 @rd`4 @0`4

    ;Swaps the high and low nibbles of both bytes in register Rd.
    swapn {rd:registers} => 0x2a @rd`4 @0`4

    ;______________________________________________________________________
    ;Stores the content of register Rs to the memory at the
    ;address [Rd]
    st  [{rd:registers}], {rs:registers} => 0x2b @rd`4 @rs`4

    ;Loads the value at memory address [Rs] to register Rd
    ld  {rd:registers}, [{rs:registers}] => 0x2c @rd`4 @rs`4
    ;______________________________________________________________________
    ;Stores the content of register Rs to memory at the
    ;location given by [const].
    st  {value: u4}, {rd:registers} =>
    {
        0x2e @value`4 @rd`4
    }
    st  {value:i16}, {rd:registers} =>
    {   
        lv = value[15:15]
        (0x8000 | value)`16 @0x2d @lv`4 @rd`4
    }
    ;______________________________________________________________________
    ;Loads the memory value at the location given by
    ;[const] to register Rd.
    ld  {rd:registers}, {value: u4} =>
    {
        0x30 @rd`4 @value`4
    }
    ld  {rd:registers}, {value:i16} =>
    {   
        lv = value[15:15]
        (0x8000 | value)`16 @0x2f @rd`4 @lv`4
    }
    ;______________________________________________________________________
    ;Stores the value at memory address (Rd +- [const]) to
    ;register Rs.
    st  [{rd:registers} + {value}], {rs:registers} =>
    {
        (0x8000 | value)`16 @0x31 @rd`4 @rs`4
    }
    st  [{rd:registers} - {value}], {rs:registers} =>
    {   
        vtemp = 0 - value
        (0x8000 | vtemp)`16 @0x31 @rd`4 @rs`4
    }
    ;______________________________________________________________________
    ;Loads the value at memory address (Rs +- [const]) to
    ;register Rd.
    ld  {rd:registers}, [{rs:registers} + {value}] =>
    {
        (0x8000 | value)`16 @0x32 @rd`4 @rs`4
    }
    ld  {rd:registers}, [{rs:registers} - {value}] =>
    {
        vtemp = 0 - value
        (0x8000 | vtemp)`16 @0x32 @rd`4 @rs`4
    }
    ;______________________________________________________________________
    ; jumps to the address given by [const] if the specified flag condition is met.  
    ; it jumps relatively if Carry flag is set
    jumpCarry {value: i16} =>
    {   
        relad = (value - pc- 2)
        lv = relad[15:15]
        (0x8000 | relad)`16 @0x34 @0`4 @lv`4
    }
    ;______________________________________________________________________
    ; jumps to the address given by [const] if the specified flag condition is met.  
    ; it jumps relatively if Zero flag is set
    jumpZero {value: i16} =>
    {   
        relad = (value - pc- 2)
        lv = relad[15:15]
        (0x8000 | relad)`16 @0x35 @0`4 @lv`4
    }
    ;______________________________________________________________________
    ; jumps to the address given by [const] if the specified flag condition is met.  
    ; it jumps relatively if Negative flag is set
    jumpNegative {value: i16} =>
    {  
        relad = (value - pc- 2)
        lv = relad[15:15]
        (0x8000 | relad)`16 @0x36 @0`4 @lv`4
    }
    ;______________________________________________________________________
    ; jumps to the address given by [const] if the specified flag condition is met.  
    ; it jumps relatively if Carry flag is not set
    jumpNotCarry {value: i16} =>
    {   
        relad = (value - pc- 2)
        lv = relad[15:15]
        (0x8000 | relad)`16 @0x37 @0`4 @lv`4
    }
    ;______________________________________________________________________
    ; jumps to the address given by [const] if the specified flag condition is met.  
    ; it jumps relatively if Zero flag is not set
    jumpNotZero {value: i16} =>
    {   
        relad = (value - pc- 2)
        lv = relad[15:15]
        (0x8000 | relad)`16 @0x38 @0`4 @lv`4
    }
    ;______________________________________________________________________
    ; jumps to the address given by [const] if the specified flag condition is met.  
    ; it jumps relatively if Negative flag is not set
    jumpNotNegative {value: i16} =>
    {       
        relad = (value - pc - 2)
        lv = relad[15:15]
        (0x8000 | relad)`16 @0x39 @0`4 @lv`4
    }
    ;______________________________________________________________________
    ; jump to the address and store current pc in Rs
    ; if there is a value in the Rs it will be overwritten
    ; so you need to store the Rs value somewhere if you want to use it later
    rcall {rd:registers}, {value:i16} =>
    {
        lv = value[15:15]
        (0x8000 | value)`16 @0x3a @rd`4 @lv`4
    }
    ; return to the address stored in Rs
    rret {rs:registers} =>
    {
        0x3b @0`4 @rs`4
    }
    ;______________________________________________________________________
    ; jump to the address given by [const] unconditionally.
    ; It jumps relatively if the target address is within -128 to 127 bytes; relative from the current pc.
    jump {value: i16} =>            
    {   
        relad = (value - pc-1)
        assert(relad <= 129)
        assert(relad >= -129)
        0x3d @relad`8
    }
    ;______________________________________________________________________
    ; jump to the address given by [const] unconditionally.
    ; it will jump to the given address; absolute
    jump {value: i16} =>           
    {   
        lv = value[15:15]
        (0x8000 | value)`16 @0x3c @0`4 @lv`4
    }

    ;peripheral access instructions
    out {value: u4}, {rd:registers} =>
    {
        0x3f @value`4 @rd`4
    }
    out {value: i16}, {rd:registers} =>
    {   
        lv = value[15:15]
        (0x8000 | value)`16 @0x3e @lv`4 @rd`4
    }

    outr [{rd:registers}], {rs:registers} =>
    {
        0x40 @rd`4 @rs`4
    }

    in  {rd:registers}, {value: i16} =>
    {   
        lv = value[15:15]
        (0x8000 | value)`16 @0x41 @rd`4 @lv`4
    }
    in  {rd:registers}, {value: u4}=>
    {
        0x42 @rd`4 @value`4
    }
    inr {rd:registers}, [{rs:registers}] =>
    {
        0x43 @rd`4 @rs`4
    }
    ; Static breakpoint instruction. Only stops when debugger static break is enabled.
    brk => 0x49 @0`4 @0`4
    ;______________________________________________________________________
    ; When an interrupt happens it will store the current pc in the PC controller.
    ; And then it will jump to the interrupt handler at address 0x0002. 
    ; When you finish handling the interrupt you need to use "reti" to jump back 
    ; to the address stored in the PC controller and continue execution.
    reti => 0x44 @0`4 @0`4
    ;______________________________________________________________________
    ;Loads the memory value at the location given by
    ; register [Rs] to register Rd
    ldf {rd:registers}, [{rs:registers}] => 0x45 @rd`4 @rs`4
    ;______________________________________________________________________
    ;Loads the memory value at the location given by
    ;[const] to register Rd.
    ldf  {rd:registers}, {value: u4} =>
    {
        0x47 @rd`4 @value`4
    }
    ldf  {rd:registers}, {value:i16} =>
    {   lv = value[15:15]
        (0x8000 | value)`16 @0x46 @rd`4 @lv`4
    }
    ;______________________________________________________________________
    ;Loads the value at memory address (Rs +- [const]) to
    ;register Rd.
    ldf  {rd:registers}, [{rs:registers} + {value}] =>
    {
        (0x8000 | value)`16 @0x48 @rd`4 @rs`4
    }
    ldf  {rd:registers}, [{rs:registers} - {value}] =>
    {
        vtemp = 0 - value
        (0x8000 | vtemp)`16 @0x48 @rd`4 @rs`4
    }


    ;--------------macros-----------------------
    ;______________________________________________________________________
    ;Put the lower 8 bits of the register Rd to the output port
    putoutput {rd:registers} => asm
    {
        out OutputReg, {rd}
    }

    ;______________________________________________________________________
    ;Read the 8 bits of the input port and put them in to the register Rd
    getinput {rd:registers} => asm
    {
        in {rd}, InputReg
    }

    ;______________________________________________________________________
    ;Read the current timer value and put them in to the register Rd
    readTimer {value: timers}, {rd:registers} => asm{
        in  {rd}, {value}
    }

    ;______________________________________________________________________
    ;Configure timer using Register R12
    configureTimer {timer:timers},{inter_enable:u1}, {reload:u1}, {prescaler:u4}, {enable:u1} => asm
    {
        assert(prescaler <= 11)
        tempval = (inter_enable << 6) | (reload << 5) | (prescaler << 1) | enable
        timerConfig = timer - 3

        ldi r12, tempval
        out timerConfig, r12

    }

    ;______________________________________________________________________
    ; Configure timer with explicit source select using Register R12
    ; source = 0 -> system clock source
    ; source = 1 -> execute_pulse source
    configureTimerSource {timer:timers},{inter_enable:u1}, {reload:u1}, {prescaler:u4}, {source:u1}, {enable:u1} => asm
    {
        assert(prescaler <= 11)
        tempval = (source << 7) | (inter_enable << 6) | (reload << 5) | (prescaler << 1) | enable
        timerConfig = timer - 3

        ldi r12, tempval
        out timerConfig, r12

    }

    ;______________________________________________________________________
    ;Set timer target using Register R12
    setTimerTarget {timer:timers}, {value:i16} => asm
    {
        timerTarget = timer - 2
        ldi r12, value
        out timerTarget, r12

    }

    ;______________________________________________________________________
    ;Reset timer using Register R12
    resetTimer {timer:timers} => asm
    {
        timerReset = timer - 1
        ldi r12, 1
        out timerReset, r12

    }

    ;______________________________________________________________________
    ;Start both timers at the same time using Register R12
    syncStartTimers => asm
    {
        ldi r12, 1
        out timerSyncStart, r12
    }

    ;Write Zero to the register Rd
    zero {rd:registers} => asm{
        ldi {rd}, 0
    }

    ;Write Zero to all registers
    zero_all => asm{
        zero r0
        zero r1
        zero r2
        zero r3
        zero r4
        zero r5
        zero r6
        zero r7
        zero r8
        zero r9
        zero r10
        zero r11
        zero r12
        zero r13
        zero r14
        zero r15
    }

    ;Decrements register Rd by one
    dec {rd:registers} => asm{
        sub {rd}, 1
    }

    ;Increments register Rd by one
    inc {rd:registers} => asm{
        add {rd}, 1
    }

pop {rd:registers}=> asm{
    ld  {rd}, [SP]
    add SP, 1
}

push{rd:registers}=> asm{
    sub SP, 1
    st  [SP], {rd}
}

ret {value}=> asm{
    ld  RA, [SP]
    add SP, {value}+1
    rret RA
}
    ;______________________________________________________________________
;sub SP, 1          ;1 instruction
;ld  RA, [$+2]      ;2 instruction
;st  [SP], RA       ;1 instruction
;jmp {value}        ;2 instruction
call {value}=>
{

    tVal = (pc+6)
    lv  = tVal[15:15]
    jlv = value[15:15]
    0x10e1 @(0x8000 | tVal)`16 @0x09f @lv`4 @0x2bef @(0x8000 | value)`16 @0x3c @0`4 @jlv`4

}



enter {value}=>asm{
    sub SP, 1
    st  [SP], BP
    mov BP, SP
    sub SP, {value}
}

enteri{value}=>asm{
    std[SP-1],r0
    in  r0, 0
    std [SP-2], r0
    sub SP, 2
}
leave => asm{
    mov SP, BP
    ld  BP, [SP]
    add SP, 1
}
leavei=>asm{
    add SP, 2
    ld  r0, [SP-2]
    out 0, r0
    ld  r0, [SP-1]
}
_scall {value} =>asm{
    sub SP, 1
    st  [SP], RA

    rcall RA, {value}
    ld  RA, [SP]
    add SP, 1
}



readRandomRange {rd:registers}, {min:i16}, {max:i16}, {rDummy1:registers}, {rDummy2:registers} => asm{
    ldi rDummy1, {min}
    ldi rDummy2, {max}
    sub rDummy2, rDummy1
    Rand rd
    and rd, rDummy2
    add rd, rDummy1
}
RandomSeed {value : i16} => asm{
    ldi r12, {value}
    out RandomSeedAddr, r12
}

enableInterrupt => asm{
    ldi r12, 1
    out CpuinterruptEnable, r12
}
disableInterrupt => asm{
    ldi r12, 0
    out CpuinterruptEnable, r12
}





}

