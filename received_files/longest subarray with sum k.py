k = 3
arr = [1, 2, 3, 1, 1, 1, 1, 4, 2, 3]

l = 0
for i in range(0, len(arr)):
	s = 0
	for j in range(i, len(arr)):
		s += arr[j]
		if s == k and l < j - i + 1:
			l = j - i + 1
		if s > k:
			break
print(l)

# random noise