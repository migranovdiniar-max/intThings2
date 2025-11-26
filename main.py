class WordPlay:
    def __init__(self, words: list):
        self.words = words

    def add_word(self, word: str):
        if word not in self.words:
            self.words += [word]

    def words_with_length(self, n: int):
        return [i for i in self.words if len(i) == n]

    def only(self, *args):
        include = []
        for i in args:
            for j in self.words:
                if i in j:
                    include += [j]



