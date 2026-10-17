module Main where

import Irving (roomies)
import System.IO

main :: IO ()
main = do
    input <- readFile "input.txt"
    let prefs :: [(String, [String])]
        prefs = read input
    
    let matches = roomies prefs
    
    writeFile "output.txt" (show matches)

    putStrLn "Matching complete. Output written to output.txt"