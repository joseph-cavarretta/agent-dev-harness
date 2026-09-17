# Deep-merge two settings objects. Objects merge recursively, arrays are unioned (so local
# permission rules and hooks survive), and scalars from the second object win.
def merge($a; $b):
  reduce ($b | keys_unsorted[]) as $k ($a;
    .[$k] = (
      if ($a[$k] | type) == "object" and ($b[$k] | type) == "object" then merge($a[$k]; $b[$k])
      elif ($a[$k] | type) == "array" and ($b[$k] | type) == "array" then ($a[$k] + $b[$k] | unique)
      else $b[$k]
      end
    ));
merge(.[0]; .[1])
