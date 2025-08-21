
while True:
    first_number = int(input('Write your first number: '))
    operation = input('Choose operation(+,-,*,/): ')
    second_number = int(input('Write your second number: '))
    if first_number or second_number != int:
        print('Write numbers!')
    elif operation !=('+','-','*','/'):
        print('Choose (+,-,*,/)!')
    if operation == '+':
        sum = first_number + second_number
        print(f'{first_number} + {second_number} = {sum} ')
    elif operation == '-':
        sum = first_number - second_number
        print(f'{first_number} - {second_number} = {sum} ')
    elif operation == '*':
        sum = first_number * second_number
        print(f'{first_number} * {second_number} = {sum} ')
    else:
        sum = first_number / second_number
        print(f'{first_number} / {second_number} = {sum}')
    continue_operation = input('Do you want to continue?(yes/no): ').lower()
    if continue_operation == 'yes':
        continue
    else:
        break
